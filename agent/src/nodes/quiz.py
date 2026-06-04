"""Quiz loop nodes.

    select_objective --> generate_mcqs --> ask_mcq (loops over MCQs) --> ...

MCQ delivery uses LangGraph ``interrupt()`` (the same mechanism as plan
approval), discriminated by a ``type`` field. The frontend renders the radio
widget, runs the wrong-answer retry loop client-side, and resolves the
interrupt ONCE with the final outcome.

Interrupt payload:   {"type": "mcq", "mcq": <MCQ dict>}
Resume value:        {"chosen_index": int, "correct": bool, "attempts": int}
"""
from __future__ import annotations

import logging
import uuid

from langchain_core.documents import Document
from langgraph.types import Command, interrupt
from pydantic import BaseModel

from src.llm import generate_structured
from src.retrieval import retrieve
from src.state import MCQ, MCQResult, Objective, SocraticState

log = logging.getLogger(__name__)


class _GenMCQ(BaseModel):
    """Structured-output schema for one generated MCQ (before id assignment)."""

    question: str
    options: list[str]
    correct_index: int
    explanation: str
    hint: str
    source_pages: list[int]


# ---------------------------------------------------------------------------
# MCQ generation (grounded)
# ---------------------------------------------------------------------------

async def build_mcqs_from_chunks(
    obj: Objective, chunks: list[Document], n: int = 2
) -> list[MCQ]:
    """Generate *n* grounded MCQs for *obj* from the provided *chunks*.

    Guarantees per MCQ:
      * exactly 4 options (truncated/padded to length 4),
      * ``correct_index`` clamped into ``[0, 3]``,
      * ``source_pages`` constrained to the pages present in *chunks*.
    """
    pages = sorted(
        {
            c.metadata.get("page")
            for c in chunks
            if c.metadata.get("page") is not None
        }
    )
    context = "\n\n".join(
        f"[p.{c.metadata.get('page')}] {c.page_content}" for c in chunks
    )

    out: list[MCQ] = []
    asked: list[str] = []
    for _ in range(n):
        avoid = ""
        if asked:
            avoid = (
                "\n\nThese questions were ALREADY asked for this objective — cover a "
                "DIFFERENT aspect and do NOT repeat them:\n- " + "\n- ".join(asked)
            )
        key_points = ", ".join(obj.key_points) if obj.key_points else ""
        g = await generate_structured(
            f"Using ONLY the source below (cite page numbers drawn from {pages}), "
            f"write one multiple-choice question for the objective '{obj.title}'. "
            + (f"Where possible, target one of these key points: {key_points}. " if key_points else "")
            + "Provide EXACTLY 4 options with exactly one correct answer, a hint that "
            "does NOT reveal the answer, and a short explanation."
            f"{avoid}\n\nSOURCE:\n{context}",
            _GenMCQ,
        )
        asked.append(g.question)
        # Constrain source pages to the pages we actually provided.
        constrained = [p for p in g.source_pages if p in pages]
        g.source_pages = constrained or pages

        # Enforce exactly 4 options. Pad with distractors if the model
        # under-produced (defensive — generation is asked for 4). Padding is a
        # generation-quality regression, so make it visible in the logs.
        opts = list(g.options[:4])
        if len(opts) < 4:
            log.warning(
                "MCQ for objective %r under-produced options (%d < 4); "
                "padding with placeholders — review generation quality.",
                obj.title,
                len(opts),
            )
        while len(opts) < 4:
            opts.append(f"Option {len(opts) + 1}")
        g.options = opts

        # Clamp correct_index into range.
        g.correct_index = max(0, min(g.correct_index, 3))

        out.append(MCQ(id=uuid.uuid4().hex, objective_id=obj.id, **g.model_dump()))
    return out


# ---------------------------------------------------------------------------
# Quiz nodes: generate ALL questions upfront, then ask them one at a time
# ---------------------------------------------------------------------------

async def generate_all_mcqs_node(state: SocraticState) -> dict:
    """Generate every question for every topic, once, right after approval.

    Producing the whole quiz upfront means the learner never sees a "preparing"
    pause between topics (just one prep step after approval). Each MCQ dict is
    enriched with UI progress fields so the widget can show "Topic N of M ·
    Question N of M" straight from the interrupt payload.
    """
    objectives = state.get("objectives", [])
    n = state.get("questions_per_objective") or 2
    topic_total = len(objectives)
    all_mcqs: list[dict] = []
    for ti, obj_dict in enumerate(objectives):
        obj = Objective(**obj_dict)
        chunks = retrieve(
            f"{obj.title}. {' '.join(obj.key_points)}",
            document_id=state["document_id"],
        )
        mcqs = await build_mcqs_from_chunks(obj, chunks, n=n)
        q_total = len(mcqs)
        for qi, m in enumerate(mcqs):
            d = m.model_dump()
            d["objective_title"] = obj.title
            d["difficulty"] = obj.difficulty
            d["topic_number"] = ti + 1
            d["topic_total"] = topic_total
            d["question_number"] = qi + 1
            d["question_total"] = q_total
            all_mcqs.append(d)
    return {"all_mcqs": all_mcqs, "current_mcq_idx": 0, "phase": "quizzing"}


def ask_mcq_node(state: SocraticState) -> Command:
    """Deliver the current question via ``interrupt()`` and record the outcome.

    The node re-runs on resume, so ``interrupt()`` is the FIRST thing it does —
    everything before it just reads state (idempotent). The resume value carries
    the user's outcome for the whole question. When the questions are exhausted,
    routes to ``summarize``; otherwise re-enters itself for the next question.
    """
    mcqs = state.get("all_mcqs", [])
    idx = state.get("current_mcq_idx", 0)
    mcq = mcqs[idx]  # already a JSON-native dict in state

    result = interrupt({"type": "mcq", "mcq": mcq})

    rec = MCQResult(
        mcq_id=mcq["id"],
        objective_id=mcq["objective_id"],
        chosen_index=result["chosen_index"],
        correct=result["correct"],
        attempts=result["attempts"],
        tutor_questions=result.get("tutor_questions", []),
    ).model_dump()

    next_idx = idx + 1
    if next_idx < len(mcqs):
        return Command(
            goto="ask_mcq",
            update={"results": [rec], "current_mcq_idx": next_idx},
        )
    return Command(
        goto="summarize",
        update={"results": [rec], "phase": "summarizing"},
    )
