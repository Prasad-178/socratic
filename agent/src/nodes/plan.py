"""Planning node — a Send map-reduce that extracts learning objectives.

Flow (subgraph):

    START --fan_out_chunks--> analyze_chunk (xN, in parallel) --> reduce --> END

``fan_out_chunks`` is a conditional edge that returns one ``Send`` per chunk,
each running ``analyze_chunk_node`` to extract candidate objectives. The
candidates accumulate via an ``operator.add`` reducer, then ``reduce_node``
dedupes them into a single :class:`Plan`.
"""
from __future__ import annotations

import operator
import uuid
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel

from src.ingest import load_chunk_texts
from src.llm import generate_structured
from src.state import Objective, Plan

_DIFFICULTY_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}


class _PlanState(TypedDict, total=False):
    """Internal state for the planning subgraph."""

    document_id: str
    chunk_texts: list[str]
    candidates: Annotated[list[Objective], operator.add]
    plan: Plan


class _ChunkObjectives(BaseModel):
    """Structured-output schema: objectives extracted from one chunk."""

    objectives: list[Objective]


# ---------------------------------------------------------------------------
# Entry: load chunk texts if not already present
# ---------------------------------------------------------------------------

def load_chunks_node(state: _PlanState) -> dict:
    """Populate ``chunk_texts`` from the document if not already supplied.

    Tests (and callers that already hold the texts) can pass ``chunk_texts``
    directly; otherwise we load them from pgvector via ``load_chunk_texts``.
    """
    if state.get("chunk_texts"):
        return {}
    return {"chunk_texts": load_chunk_texts(state["document_id"])}


# ---------------------------------------------------------------------------
# Map: fan out one Send per chunk
# ---------------------------------------------------------------------------

def fan_out_chunks(state: _PlanState) -> list[Send]:
    """Conditional edge: emit one ``Send`` to ``analyze_chunk`` per chunk."""
    return [Send("analyze_chunk", {"chunk": c}) for c in state.get("chunk_texts", [])]


async def analyze_chunk_node(payload: dict) -> dict:
    """Extract 1-2 candidate objectives from a single chunk."""
    res = await generate_structured(
        "Extract 1-2 distinct learning objectives from the text below. "
        "For each, provide a concise title, a one-sentence description, a "
        "difficulty of beginner|intermediate|advanced, and 1-3 key_points. "
        "Use a short unique id for each.\n\n"
        f"TEXT:\n{payload['chunk']}",
        _ChunkObjectives,
    )
    for o in res.objectives:
        if not o.id:
            o.id = uuid.uuid4().hex
    return {"candidates": res.objectives}


# ---------------------------------------------------------------------------
# Reduce: dedupe candidates into a Plan (PURE)
# ---------------------------------------------------------------------------

def reduce_objectives(candidates: list[Objective]) -> Plan:
    """Dedupe objectives by title and compute the overall difficulty.

    Pure function — no I/O. Difficulty is the max difficulty across the
    deduped objectives. Returns an empty-but-valid plan when given no
    candidates.
    """
    seen: set[str] = set()
    merged: list[Objective] = []
    for o in candidates:
        key = o.title.strip().lower()
        if key and key not in seen:
            seen.add(key)
            merged.append(o)
    overall = max(
        (o.difficulty for o in merged),
        key=lambda d: _DIFFICULTY_ORDER[d],
        default="beginner",
    )
    return Plan(
        objectives=merged,
        overall_difficulty=overall,
        summary=f"{len(merged)} objectives covering the document.",
    )


def reduce_node(state: _PlanState) -> dict:
    """Reduce accumulated candidates into a single Plan."""
    return {"plan": reduce_objectives(state.get("candidates", []))}


# ---------------------------------------------------------------------------
# Subgraph factory
# ---------------------------------------------------------------------------

def make_plan_subgraph():
    """Compile the planning map-reduce subgraph.

    The compiled graph reads ``document_id``/``chunk_texts`` from state and
    writes ``plan`` (and ``chunk_texts`` if it had to load them).
    """
    g = StateGraph(_PlanState)
    g.add_node("load_chunks", load_chunks_node)
    g.add_node("analyze_chunk", analyze_chunk_node)
    g.add_node("reduce", reduce_node)
    g.add_edge(START, "load_chunks")
    g.add_conditional_edges("load_chunks", fan_out_chunks, ["analyze_chunk"])
    g.add_edge("analyze_chunk", "reduce")
    g.add_edge("reduce", END)
    return g.compile()
