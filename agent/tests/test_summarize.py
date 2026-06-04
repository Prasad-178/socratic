"""Unit tests for the summarize report (PURE) and summarize_node output shape."""
import pytest
from langchain_core.messages import AIMessage

import src.nodes.summarize as summarize_mod
from src.nodes.summarize import compute_report
from src.state import MCQResult


def test_compute_report_scores_and_flags_weak_objectives():
    results = [
        MCQResult(mcq_id="1", objective_id="o1", chosen_index=0, correct=True, attempts=1),
        MCQResult(mcq_id="2", objective_id="o2", chosen_index=1, correct=True, attempts=3),
    ]
    report = compute_report(results)
    assert report["total"] == 2
    assert report["correct"] == 2
    # o2 needed 3 attempts for 1 question -> retried -> weak; o1 was 1-for-1.
    assert report["weak_objectives"] == ["o2"]


def test_compute_report_orders_weak_by_most_retries():
    results = [
        MCQResult(mcq_id="1", objective_id="o1", chosen_index=0, correct=True, attempts=2),
        MCQResult(mcq_id="2", objective_id="o2", chosen_index=1, correct=False, attempts=4),
        MCQResult(mcq_id="3", objective_id="o3", chosen_index=2, correct=True, attempts=1),
    ]
    report = compute_report(results)
    # o2 (4 attempts) before o1 (2 attempts); o3 (1-for-1) not weak.
    assert report["weak_objectives"] == ["o2", "o1"]
    assert "o3" not in report["weak_objectives"]


def test_compute_report_counts_incorrect():
    results = [
        MCQResult(mcq_id="1", objective_id="o1", chosen_index=0, correct=True, attempts=1),
        MCQResult(mcq_id="2", objective_id="o1", chosen_index=1, correct=False, attempts=1),
    ]
    report = compute_report(results)
    assert report["total"] == 2
    assert report["correct"] == 1
    assert report["by_objective"]["o1"] == {"attempts": 2, "correct": 1, "n": 2}


# ---------------------------------------------------------------------------
# summarize_node output shape
# ---------------------------------------------------------------------------

class _FakeChat:
    async def ainvoke(self, _prompt):
        return AIMessage(content="Tip A. Tip B. Tip C.")


@pytest.mark.asyncio
async def test_summarize_node_persists_summary_and_report(monkeypatch):
    """summarize_node must return summary (str) and report (dict) alongside messages."""
    monkeypatch.setattr(summarize_mod, "get_chat_model", lambda **kw: _FakeChat())

    from src.nodes.summarize import summarize_node

    state = {
        "results": [
            {"mcq_id": "1", "objective_id": "o1", "chosen_index": 0, "correct": True, "attempts": 1},
        ]
    }
    out = await summarize_node(state)

    assert out["phase"] == "done"
    # summary must be a plain string (JSON-serialisable)
    assert isinstance(out["summary"], str)
    assert "Tip A" in out["summary"]
    # report must contain the expected keys
    assert isinstance(out["report"], dict)
    assert out["report"]["total"] == 1
    assert out["report"]["correct"] == 1
    assert "by_objective" in out["report"]
    assert "weak_objectives" in out["report"]
    # messages list must still contain the AIMessage (for the add_messages reducer)
    assert len(out["messages"]) == 1
