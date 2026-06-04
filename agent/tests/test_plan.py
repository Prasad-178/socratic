"""Unit tests for the plan reducer (PURE — no monkeypatch needed)."""
from src.nodes.plan import reduce_objectives
from src.state import Objective


def _obj(oid: str, title: str, difficulty: str) -> Objective:
    return Objective(
        id=oid,
        title=title,
        description="d",
        difficulty=difficulty,  # type: ignore[arg-type]
        key_points=[],
    )


def test_reduce_objectives_dedupes_by_title():
    raw = [
        _obj("1", "A", "beginner"),
        _obj("2", "a", "beginner"),  # same title (case-insensitive) -> deduped
        _obj("3", "B", "advanced"),
    ]
    plan = reduce_objectives(raw)
    titles = [o.title for o in plan.objectives]
    assert len(plan.objectives) == 2
    assert titles == ["A", "B"]


def test_reduce_objectives_overall_difficulty_is_max():
    raw = [
        _obj("1", "A", "beginner"),
        _obj("2", "B", "advanced"),
        _obj("3", "C", "intermediate"),
    ]
    plan = reduce_objectives(raw)
    assert plan.overall_difficulty == "advanced"


def test_reduce_objectives_empty_is_valid():
    plan = reduce_objectives([])
    assert plan.objectives == []
    assert plan.overall_difficulty in ("beginner", "intermediate", "advanced")
    assert "0 objectives" in plan.summary
