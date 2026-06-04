"""HITL plan-approval interrupt: surface, resume(approve), advance to quiz.

Drives the compiled graph offline with InMemorySaver. The only LLM/IO touched
after approval is generate_mcqs (retrieve + generate_structured), both
monkeypatched.
"""
import src.nodes.quiz as quiz
from langchain_core.documents import Document
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.graph import build_graph
from src.nodes.quiz import _GenMCQ


def _seed_state() -> dict:
    return {
        "document_id": "doc1",
        "plan": {
            "objectives": [
                {
                    "id": "1",
                    "title": "A",
                    "description": "d",
                    "difficulty": "beginner",
                    "key_points": [],
                    "status": "pending",
                }
            ],
            "overall_difficulty": "beginner",
            "summary": "s",
        },
        "objectives": [],
        "phase": "awaiting_approval",
    }


def _patch_mcq_generation(monkeypatch):
    def fake_retrieve(query, *, document_id, **kwargs):
        return [Document(page_content="context text", metadata={"page": 1})]

    async def fake_gen(prompt, schema, **kwargs):
        return _GenMCQ(
            question="q",
            options=["a", "b", "c", "d"],
            correct_index=0,
            explanation="e",
            hint="h",
            source_pages=[1],
        )

    monkeypatch.setattr(quiz, "retrieve", fake_retrieve)
    monkeypatch.setattr(quiz, "generate_structured", fake_gen)


async def test_plan_approval_interrupt_surfaces():
    graph = build_graph().compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "t-surface"}}
    r = await graph.ainvoke(_seed_state(), cfg)
    assert r.get("__interrupt__"), "expected an interrupt"
    payload = r["__interrupt__"][0].value
    assert payload["type"] == "plan_approval"
    assert payload["plan"][0]["title"] == "A"


async def test_plan_approval_resume_applies_edits_and_advances(monkeypatch):
    _patch_mcq_generation(monkeypatch)
    graph = build_graph().compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "t-approve"}}

    r = await graph.ainvoke(_seed_state(), cfg)
    assert r["__interrupt__"][0].value["type"] == "plan_approval"

    edited = [
        {
            "id": "1",
            "title": "A2",
            "description": "d",
            "difficulty": "beginner",
            "key_points": [],
            "status": "pending",
        }
    ]
    r = await graph.ainvoke(Command(resume={"action": "approve", "plan": edited}), cfg)

    # State after approval reflects the edit and is in the quiz phase.
    state = graph.get_state(cfg).values
    assert state["plan_status"] == "approved"
    assert state["objectives"][0].title == "A2"

    # It advanced into the quiz: the next interrupt is an MCQ.
    assert r.get("__interrupt__"), "expected to advance to the MCQ interrupt"
    assert r["__interrupt__"][0].value["type"] == "mcq"


async def test_plan_approval_regenerate_routes_back_to_plan(monkeypatch):
    # Regenerate sends control back to the plan node. Stub the plan subgraph so
    # we don't hit the DB; assert it re-enters planning and re-surfaces approval.
    import src.graph as graph_mod

    class _FakeSub:
        async def ainvoke(self, _in):
            return {
                "plan": {
                    "objectives": [
                        {
                            "id": "9",
                            "title": "Regen",
                            "description": "d",
                            "difficulty": "beginner",
                            "key_points": [],
                            "status": "pending",
                        }
                    ],
                    "overall_difficulty": "beginner",
                    "summary": "regen",
                }
            }

    monkeypatch.setattr(graph_mod, "_plan_subgraph", _FakeSub())

    graph = build_graph().compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "t-regen"}}

    r = await graph.ainvoke(_seed_state(), cfg)
    assert r["__interrupt__"][0].value["type"] == "plan_approval"

    r = await graph.ainvoke(
        Command(resume={"action": "regenerate", "feedback": "more detail"}), cfg
    )
    # Back to a fresh plan-approval interrupt with the regenerated plan.
    assert r["__interrupt__"][0].value["type"] == "plan_approval"
    assert r["__interrupt__"][0].value["plan"][0]["title"] == "Regen"
