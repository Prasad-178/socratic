"""Summarize node — progress report + LLM study tips."""
from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from src.llm import generate_structured
from src.state import MCQResult, SocraticState


class _StudyTips(BaseModel):
    """Structured (markdown-free) summary the UI renders as a clean list."""

    headline: str = Field(description="One warm, encouraging one-line summary.")
    tips: list[str] = Field(
        description="3 concise, actionable study tips. Plain sentences, NO markdown."
    )


def compute_report(results: list[MCQResult | dict]) -> dict:
    """Aggregate quiz results into a score report (PURE — no I/O).

    Accepts either ``MCQResult`` instances or their dumped dicts (state stores
    dicts; unit tests pass models). Dicts are validated through ``MCQResult``.

    Returns:
        ``total``           — number of MCQs answered.
        ``correct``         — number answered correctly.
        ``by_objective``    — per-objective ``{attempts, correct, n}``.
        ``weak_objectives`` — objective ids that needed retries (took more
                              attempts than questions), ordered most-retried
                              first.
    """
    results = [r if isinstance(r, MCQResult) else MCQResult(**r) for r in results]
    by_obj: dict[str, dict[str, int]] = defaultdict(
        lambda: {"attempts": 0, "correct": 0, "n": 0}
    )
    for r in results:
        b = by_obj[r.objective_id]
        b["attempts"] += r.attempts
        b["n"] += 1
        b["correct"] += int(r.correct)

    weak = sorted(
        by_obj,
        key=lambda k: by_obj[k]["attempts"],
        reverse=True,
    )
    weak = [k for k in weak if by_obj[k]["attempts"] > by_obj[k]["n"]]

    return {
        "total": len(results),
        "correct": sum(int(r.correct) for r in results),
        "by_objective": {k: dict(v) for k, v in by_obj.items()},
        "weak_objectives": weak,
    }


async def summarize_node(state: SocraticState) -> dict:
    """Produce a final report and STRUCTURED study tips.

    Persists a one-line ``headline``, a list of ``study_tips`` (markdown-free,
    so Summary.tsx renders a clean list), and the structured score ``report``.
    """
    results = state.get("results", [])
    report = compute_report(results)
    # Map objective ids -> human-readable topic titles so tips never leak a raw
    # identifier like "OBJ002"; the LLM only ever sees the titles.
    id_to_title = {
        o.get("id"): o.get("title", "this topic") for o in state.get("objectives", [])
    }
    # Topics the learner struggled with: weak (most retries) first, then any other
    # topic they got wrong or needed more than one attempt on.
    struggled_ids = {
        r["objective_id"] for r in results if (not r["correct"]) or r["attempts"] > 1
    }
    ordered = report["weak_objectives"] + [
        i for i in struggled_ids if i not in report["weak_objectives"]
    ]
    struggled = [id_to_title.get(i, "this topic") for i in ordered]
    focus = (
        ", ".join(f'"{t}"' for t in struggled)
        if struggled
        else "none in particular — they did well across the board"
    )
    # What they asked the tutor — direct signals of what confused them.
    tutor_qs = [q for r in results for q in r.get("tutor_questions", [])]
    tutor_ctx = (
        " They also asked their tutor these questions (signals of confusion): "
        + "; ".join(f'"{q}"' for q in tutor_qs[:8])
        + "."
        if tutor_qs
        else ""
    )
    tips = await generate_structured(
        "Write an encouraging summary and study plan for a learner who just "
        f"finished a quiz, scoring {report['correct']} out of {report['total']}. "
        f"The topics they struggled with (got wrong or needed retries): {focus}.{tutor_ctx} "
        "Give one warm headline and exactly 3 SPECIFIC, actionable next steps — base "
        "each on these signals, naming the exact topic or idea to review and a "
        "concrete action. Refer to topics by NAME only — never use codes, ids, or "
        "identifiers. Plain sentences only — no markdown, no bullet characters.",
        _StudyTips,
    )
    return {
        "phase": "done",
        "headline": tips.headline,
        "study_tips": tips.tips,
        "report": report,
    }
