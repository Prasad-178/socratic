"""Durable HITL proof against a live Postgres (AsyncPostgresSaver).

Mirrors the offline ``test_interrupt`` flow but persists the checkpoint to
Postgres: seed a plan -> invoke to the ``plan_approval`` interrupt -> resume on
the SAME ``thread_id`` and assert the graph advances into the quiz loop. The
resume reloads state purely from the Postgres checkpoint, exercising the full
msgpack serde round-trip.

Also asserts NO "unregistered type" warning is emitted — that warning is what
the dict-state refactor eliminated, and this is the durable-path proof it holds.

Marked ``integration``: needs ``docker compose up -d db``. Run with:
    uv run pytest -m integration tests/test_durable_hitl_integration.py -q
"""
import uuid
import warnings

import pytest
import src.nodes.quiz as quiz
from langchain_core.documents import Document
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.graph import build_graph
from src.nodes.quiz import _GenMCQ
from src.settings import settings

pytestmark = pytest.mark.integration


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


async def test_durable_plan_approval_resume_advances(monkeypatch):
    _patch_mcq_generation(monkeypatch)

    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    pool = AsyncConnectionPool(
        conninfo=dsn,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()
        graph = build_graph().compile(checkpointer=saver)

        # Unique thread per run so reruns don't resume a stale checkpoint.
        cfg = {"configurable": {"thread_id": f"durable-{uuid.uuid4().hex}"}}

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            # 1) Invoke to the plan-approval interrupt (state persisted to PG).
            r = await graph.ainvoke(_seed_state(), cfg)
            assert r["__interrupt__"][0].value["type"] == "plan_approval"

            # 2) Resume on the SAME thread_id; state is rehydrated from Postgres.
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
            r = await graph.ainvoke(
                Command(resume={"action": "approve", "plan": edited}), cfg
            )

        # Advanced into the quiz: next interrupt is an MCQ, edit applied.
        state = (await graph.aget_state(cfg)).values
        assert state["plan_status"] == "approved"
        assert state["objectives"][0]["title"] == "A2"
        assert r.get("__interrupt__"), "expected to advance to the MCQ interrupt"
        assert r["__interrupt__"][0].value["type"] == "mcq"

        # Durable-serde proof: no msgpack "unregistered type" warning anywhere.
        offenders = [
            str(w.message)
            for w in caught
            if "unregistered type" in str(w.message).lower()
        ]
        assert not offenders, f"unexpected unregistered-type warning(s): {offenders}"
    finally:
        await pool.close()
