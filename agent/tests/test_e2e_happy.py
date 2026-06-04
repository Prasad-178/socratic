"""End-to-end happy path, fully offline (everything monkeypatched).

Flow driven via interrupts:
  plan map-reduce (2 objectives) -> approve -> obj1 MCQ -> obj2 MCQ -> summarize.

Seams monkeypatched:
  * src.nodes.plan.generate_structured  -> 1 objective per chunk (2 chunks)
  * src.nodes.quiz.retrieve             -> fake grounded chunk
  * src.nodes.quiz.generate_structured  -> 1 canned MCQ
  * src.nodes.summarize.get_chat_model  -> fake chat returning a tips message
"""
import src.nodes.plan as plan_mod
import src.nodes.quiz as quiz_mod
import src.nodes.summarize as summarize_mod
from langchain_core.documents import Document
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.graph import build_graph
from src.nodes.plan import _ChunkObjectives, _ConsolidatedPlan
from src.nodes.quiz import _GenMCQ
from src.nodes.summarize import _StudyTips
from src.state import Objective


async def _fake_summary_gen(prompt, schema, **kwargs):
    return _StudyTips(headline="Great job!", tips=["Tip 1", "Tip 2", "Tip 3"])


def _install_fakes(monkeypatch):
    # --- plan: one distinct objective per chunk ---
    _counter = {"n": 0}

    def _obj(i):
        return Objective(
            id=f"o{i}", title=f"Objective {i}", description="d",
            difficulty="beginner", key_points=["k"],
        )

    async def fake_plan_gen(prompt, schema, **kwargs):
        # The reduce step now runs an LLM consolidation pass over the candidates.
        if schema is _ConsolidatedPlan:
            return _ConsolidatedPlan(objectives=[_obj(1), _obj(2)], summary="two objectives")
        # Otherwise it's the per-chunk extraction: one distinct objective per chunk.
        _counter["n"] += 1
        return _ChunkObjectives(objectives=[_obj(_counter["n"])])

    monkeypatch.setattr(plan_mod, "generate_structured", fake_plan_gen)

    # --- quiz: fake retrieval + one canned MCQ per objective ---
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

    # --- summarize: fake structured study tips ---
    monkeypatch.setattr(summarize_mod, "generate_structured", _fake_summary_gen)


async def test_e2e_happy_path(monkeypatch):
    _install_fakes(monkeypatch)

    graph = build_graph().compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "e2e"}}

    # Seed with chunk_texts so planning fans out without touching the DB.
    # Two chunks -> two objectives -> n=1 MCQ each (override via build limit
    # below is not needed; we just answer the first MCQ of each objective and
    # let the loop walk all generated MCQs).
    seed = {"document_id": "doc1", "chunk_texts": ["chunk one", "chunk two"]}

    # 1) Run planning -> plan-approval interrupt.
    r = await graph.ainvoke(seed, cfg)
    assert r["__interrupt__"][0].value["type"] == "plan_approval"
    objectives = r["__interrupt__"][0].value["plan"]
    assert len(objectives) == 2  # one per chunk, deduped titles differ

    # 2) Approve the plan (unedited).
    r = await graph.ainvoke(
        Command(resume={"action": "approve", "plan": objectives}), cfg
    )

    # 3) Drive every MCQ interrupt with a correct answer until we reach `done`.
    guard = 0
    while r.get("__interrupt__"):
        guard += 1
        assert guard < 20, "too many interrupts — possible loop"
        payload = r["__interrupt__"][0].value
        assert payload["type"] == "mcq"
        mcq = payload["mcq"]
        # Answer correctly on the first attempt.
        r = await graph.ainvoke(
            Command(
                resume={
                    "chosen_index": mcq["correct_index"],
                    "correct": True,
                    "attempts": 1,
                }
            ),
            cfg,
        )

    # 4) Final state: done + results populated for every MCQ answered.
    final = graph.get_state(cfg).values
    assert final["phase"] == "done"
    assert len(final["results"]) == guard
    # results are stored as JSON-native dicts (msgpack-clean for durable HITL)
    assert all(res["correct"] for res in final["results"])
    # Structured study tips + headline were persisted (markdown-free).
    assert final["study_tips"][0] == "Tip 1"
    assert final["headline"]
