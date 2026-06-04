"""Summarize node — progress report + LLM study tips."""
from __future__ import annotations

from collections import defaultdict

from src.llm import get_chat_model
from src.state import MCQResult, SocraticState


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
    """Produce a final report and LLM-generated study tips."""
    report = compute_report(state.get("results", []))
    tips = await get_chat_model().ainvoke(
        "Give 3 concise, personalized study tips for a learner who scored "
        f"{report['correct']}/{report['total']} on a quiz. The objective ids "
        f"they struggled with most (needed retries): {report['weak_objectives']}. "
        "Keep it warm and actionable."
    )
    return {
        "phase": "done",
        "messages": [tips],
    }
