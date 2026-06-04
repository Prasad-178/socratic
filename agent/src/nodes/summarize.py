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
    report = compute_report(state.get("results", []))
    # Map objective ids -> human-readable topic titles so the tips never leak a
    # raw identifier like "OBJ002". The LLM only ever sees the titles.
    id_to_title = {
        o.get("id"): o.get("title", "this topic") for o in state.get("objectives", [])
    }
    weak_titles = [id_to_title.get(oid, "this topic") for oid in report["weak_objectives"]]
    focus = (
        ", ".join(f'"{t}"' for t in weak_titles)
        if weak_titles
        else "none in particular — they did well across the board"
    )
    tips = await generate_structured(
        "Write an encouraging summary for a learner who just finished a quiz, "
        f"scoring {report['correct']} out of {report['total']}. "
        f"The topics they found hardest (needed the most retries): {focus}. "
        "Give one warm headline and exactly 3 concise, actionable study tips. "
        "Refer to any topic by its NAME only — never use codes, ids, or identifiers. "
        "Plain sentences only — no markdown, no bullet characters.",
        _StudyTips,
    )
    return {
        "phase": "done",
        "headline": tips.headline,
        "study_tips": tips.tips,
        "report": report,
    }
