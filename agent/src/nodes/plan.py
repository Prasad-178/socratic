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

# The map step over-produces (1-2 objectives per chunk); cap the consolidated
# lesson so the quiz stays a reasonable length.
MAX_OBJECTIVES = 6


class _PlanState(TypedDict, total=False):
    """Internal state for the planning subgraph.

    ``plan`` is stored as a plain dict (``Plan.model_dump()``) so the value that
    flows back into ``SocraticState`` stays JSON-native and the durable msgpack
    checkpoint carries no unregistered Pydantic types. ``candidates`` holds
    ``Objective`` instances only transiently while the map-reduce runs.
    """

    document_id: str
    chunk_texts: list[str]
    candidates: Annotated[list[Objective], operator.add]
    plan: dict


class _ChunkObjectives(BaseModel):
    """Structured-output schema: objectives extracted from one chunk."""

    objectives: list[Objective]


class _ConsolidatedPlan(BaseModel):
    """Structured-output schema: the consolidated, deduplicated objective set."""

    objectives: list[Objective]
    summary: str


_CONSOLIDATE_PROMPT = (
    "You are designing a single coherent lesson. Below are candidate learning "
    "objectives extracted independently from different parts of one document, so "
    "many overlap or duplicate each other.\n\n"
    "Consolidate them into AT MOST {n} DISTINCT, non-overlapping objectives that "
    "together cover the material, ordered from foundational to advanced. Merge "
    "duplicates and near-duplicates into a single objective. Each needs a clear "
    "title, a one-sentence description, a difficulty (beginner|intermediate|"
    "advanced), 2-4 key_points, and a short unique id. Also write a one-sentence "
    "lesson summary.\n\nCANDIDATE OBJECTIVES:\n{listing}"
)


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

def _plan_from(objectives: list[Objective], summary: str | None = None) -> Plan:
    """Build a Plan from objectives, deriving the overall difficulty."""
    overall = max(
        (o.difficulty for o in objectives),
        key=lambda d: _DIFFICULTY_ORDER[d],
        default="beginner",
    )
    return Plan(
        objectives=objectives,
        overall_difficulty=overall,
        summary=summary or f"{len(objectives)} objectives covering the document.",
    )


def reduce_objectives(candidates: list[Objective]) -> Plan:
    """Dedupe objectives by exact title (pure pre-filter / fallback).

    Pure function — no I/O. Used to shrink the candidate set before the LLM
    consolidation pass and as the fallback if that pass fails.
    """
    seen: set[str] = set()
    merged: list[Objective] = []
    for o in candidates:
        key = o.title.strip().lower()
        if key and key not in seen:
            seen.add(key)
            merged.append(o)
    return _plan_from(merged)


async def reduce_node(state: _PlanState) -> dict:
    """Consolidate accumulated candidates into a clean, capped Plan.

    The map step over-produces (1-2 objectives per chunk, with heavy semantic
    overlap on real documents) and a pure title-dedup can't merge objectives
    that say the same thing in different words. So we run one LLM consolidation
    pass into <= MAX_OBJECTIVES distinct objectives, ordered foundational ->
    advanced. Falls back to the pure title-dedup (capped) if the call fails.
    """
    pre = reduce_objectives(state.get("candidates", [])).objectives
    if len(pre) <= 1:
        return {"plan": _plan_from(pre).model_dump()}

    listing = "\n".join(f"- [{o.difficulty}] {o.title}: {o.description}" for o in pre)
    try:
        result = await generate_structured(
            _CONSOLIDATE_PROMPT.format(n=MAX_OBJECTIVES, listing=listing),
            _ConsolidatedPlan,
        )
        objs = result.objectives[:MAX_OBJECTIVES]
        for o in objs:
            if not o.id:
                o.id = uuid.uuid4().hex
        if not objs:
            raise ValueError("consolidation produced no objectives")
        plan = _plan_from(objs, summary=result.summary)
    except Exception:
        plan = _plan_from(pre[:MAX_OBJECTIVES])
    return {"plan": plan.model_dump()}


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
