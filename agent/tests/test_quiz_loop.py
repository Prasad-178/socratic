"""Within-objective multi-MCQ advance (offline).

One objective generates ``n=2`` MCQs; both ``mcq`` interrupts are driven and we
assert that:
  * two results accumulate (``len(results) == 2``),
  * each result references a distinct ``mcq_id``,
  * ``current_objective_idx`` advances exactly once (0 -> 1) — i.e. the loop
    re-enters ``ask_mcq`` for the second MCQ *before* moving to the next
    objective.

Reuses the monkeypatch seams from ``test_e2e_happy.py`` (fake retrieve + canned
MCQ generation), but starts from a seeded, pre-approved single-objective plan so
the focus is squarely on the intra-objective MCQ loop.
"""
import src.nodes.quiz as quiz_mod
import src.nodes.summarize as summarize_mod
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.graph import build_graph
from src.nodes.quiz import _GenMCQ


class _FakeChat:
    async def ainvoke(self, _prompt):
        return AIMessage(content="Tip 1. Tip 2. Tip 3.")


def _seed_one_objective() -> dict:
    """A plan with exactly one objective, awaiting approval."""
    return {
        "document_id": "doc1",
        "plan": {
            "objectives": [
                {
                    "id": "o1",
                    "title": "Only objective",
                    "description": "d",
                    "difficulty": "beginner",
                    "key_points": ["k"],
                    "status": "pending",
                }
            ],
            "overall_difficulty": "beginner",
            "summary": "s",
        },
        "objectives": [],
        "phase": "awaiting_approval",
    }


def _install_quiz_fakes(monkeypatch):
    def fake_retrieve(query, *, document_id, **kwargs):
        return [Document(page_content="ctx", metadata={"page": 1})]

    async def fake_quiz_gen(prompt, schema, **kwargs):
        return _GenMCQ(
            question="q",
            options=["a", "b", "c", "d"],
            correct_index=0,
            explanation="e",
            hint="h",
            source_pages=[1],
        )

    monkeypatch.setattr(quiz_mod, "retrieve", fake_retrieve)
    monkeypatch.setattr(quiz_mod, "generate_structured", fake_quiz_gen)
    monkeypatch.setattr(summarize_mod, "get_chat_model", lambda **kw: _FakeChat())


async def test_within_objective_multi_mcq_advance(monkeypatch):
    _install_quiz_fakes(monkeypatch)

    graph = build_graph().compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "multi-mcq"}}

    # 1) Surface plan approval for the single seeded objective.
    r = await graph.ainvoke(_seed_one_objective(), cfg)
    assert r["__interrupt__"][0].value["type"] == "plan_approval"
    objectives = r["__interrupt__"][0].value["plan"]
    assert len(objectives) == 1

    # 2) Approve -> generate_mcqs builds n=2 MCQs -> first mcq interrupt.
    r = await graph.ainvoke(
        Command(resume={"action": "approve", "plan": objectives}), cfg
    )
    assert r["__interrupt__"][0].value["type"] == "mcq"

    # While on the (single) objective, idx must still be 0.
    assert graph.get_state(cfg).values["current_objective_idx"] == 0

    seen_mcq_ids: list[str] = []
    guard = 0
    while r.get("__interrupt__"):
        guard += 1
        assert guard < 10, "too many interrupts — loop did not advance"
        payload = r["__interrupt__"][0].value
        assert payload["type"] == "mcq"
        seen_mcq_ids.append(payload["mcq"]["id"])
        r = await graph.ainvoke(
            Command(
                resume={
                    "chosen_index": payload["mcq"]["correct_index"],
                    "correct": True,
                    "attempts": 1,
                }
            ),
            cfg,
        )

    final = graph.get_state(cfg).values

    # Exactly two MCQs were asked, with distinct ids.
    assert len(seen_mcq_ids) == 2
    assert len(set(seen_mcq_ids)) == 2, "mcq ids must be unique"

    # Two results accumulated, one per MCQ, with matching unique ids.
    results = final["results"]
    assert len(results) == 2
    assert {r["mcq_id"] for r in results} == set(seen_mcq_ids)
    assert all(res["correct"] for res in results)

    # The objective index advanced exactly once (the second MCQ re-entered
    # ask_mcq on the SAME objective; only after exhausting both did it move on).
    assert final["current_objective_idx"] == 1

    # No more objectives -> the run summarized.
    assert final["phase"] == "done"
