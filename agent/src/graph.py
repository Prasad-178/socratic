"""Graph assembly: plan map-reduce -> HITL approval -> quiz loop -> summarize.

Wiring (high level):

    START
      |
      v
    route_entry ----(plan exists)----> approve_plan
      |                                     |
    (no plan)                       approve / regenerate
      |                                /          \\
      v                              /            v
    plan (map-reduce subgraph) <---+        select_objective
      |                                       /        \\
      +--> approve_plan              (exhausted)     (more)
                                          |               \\
                                          v                v
                                      summarize <----  generate_mcqs
                                          |                  |
                                          v                  v
                                         END             ask_mcq (loops via interrupt)
                                                              |
                                                  (objective done) -> select_objective

Both human-in-the-loop steps (plan approval and each MCQ) use LangGraph
``interrupt()``, discriminated by a ``type`` field in the payload, so the whole
graph is drivable offline with ``InMemorySaver`` + scripted ``Command(resume=...)``.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.nodes.plan import make_plan_subgraph
from src.nodes.quiz import (
    ask_mcq_node,
    generate_mcqs_node,
    select_objective_node,
)
from src.nodes.summarize import summarize_node
from src.state import Objective, Plan, SocraticState


# ---------------------------------------------------------------------------
# Entry routing
# ---------------------------------------------------------------------------

def route_entry(state: SocraticState) -> str:
    """Skip planning when a plan is already present (e.g. seeded state)."""
    if state.get("plan") is not None:
        return "approve_plan"
    return "plan"


# ---------------------------------------------------------------------------
# HITL: plan approval (interrupt-based, thin + idempotent)
# ---------------------------------------------------------------------------

def _plan_objectives(state: SocraticState) -> list[dict]:
    """Objectives to present for approval, as plain JSON-native dicts."""
    plan = state.get("plan")
    if isinstance(plan, Plan):
        return [o.model_dump() for o in plan.objectives]
    if isinstance(plan, dict):
        return plan.get("objectives", [])
    objs = state.get("objectives", [])
    return [o.model_dump() if isinstance(o, Objective) else o for o in objs]


def approve_plan_node(state: SocraticState) -> Command:
    """Surface the plan for human approval; route on the resume decision.

    interrupt payload: {"type": "plan_approval", "plan": <objectives>}
    resume value:      {"action": "approve"|"regenerate",
                        "plan": <edited objectives>, "feedback": <str>}

    Objectives are stored in state as dicts; we validate each through
    ``Objective`` (so an edited payload is normalised + schema-checked) and
    write the dumped dicts back.
    """
    decision = interrupt({"type": "plan_approval", "plan": _plan_objectives(state)})

    if decision["action"] == "approve":
        edited = decision.get("plan") or _plan_objectives(state)
        objectives = [
            (o if isinstance(o, Objective) else Objective(**o)).model_dump()
            for o in edited
        ]
        return Command(
            goto="select_objective",
            update={
                "objectives": objectives,
                "plan_status": "approved",
                "current_objective_idx": 0,
                "phase": "quizzing",
            },
        )
    # regenerate
    return Command(
        goto="plan",
        update={
            "plan": None,
            "plan_status": "rejected",
            "feedback": decision.get("feedback"),
        },
    )


# ---------------------------------------------------------------------------
# Plan node wrapper: run the map-reduce subgraph, then go to approval
# ---------------------------------------------------------------------------

_plan_subgraph = make_plan_subgraph()


async def plan_node(state: SocraticState) -> Command:
    """Run the planning map-reduce subgraph and route to approval.

    Passes through ``document_id``/``chunk_texts`` so the subgraph can fan out;
    writes back the resulting ``plan``.
    """
    sub_in = {"document_id": state.get("document_id")}
    if state.get("chunk_texts"):
        sub_in["chunk_texts"] = state["chunk_texts"]
    result = await _plan_subgraph.ainvoke(sub_in)
    return Command(
        goto="approve_plan",
        update={"plan": result.get("plan"), "phase": "awaiting_approval"},
    )


# ---------------------------------------------------------------------------
# Build / compile
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """Construct (but do not compile) the full Socratic agent graph.

    Nodes that route via ``Command(goto=...)`` declare their possible
    destinations so the static graph is complete (correct rendering /
    validation under ``langgraph dev``).
    """
    g = StateGraph(SocraticState)

    g.add_node("plan", plan_node, destinations=("approve_plan",))
    g.add_node(
        "approve_plan",
        approve_plan_node,
        destinations=("select_objective", "plan"),
    )
    g.add_node(
        "select_objective",
        select_objective_node,
        destinations=("generate_mcqs", "summarize"),
    )
    g.add_node("generate_mcqs", generate_mcqs_node)
    g.add_node("ask_mcq", ask_mcq_node, destinations=("ask_mcq", "select_objective"))
    g.add_node("summarize", summarize_node)

    g.add_conditional_edges(START, route_entry, ["plan", "approve_plan"])
    # plan -> approve_plan and approve_plan -> {select_objective, plan} are
    # handled by Command(goto=...) returned from the nodes; select_objective,
    # ask_mcq likewise route via Command. generate_mcqs falls through to
    # ask_mcq with a static edge.
    g.add_edge("generate_mcqs", "ask_mcq")
    g.add_edge("summarize", END)

    return g


def compile_graph(checkpointer=None):
    """Compile the graph with *checkpointer* (defaults to an in-memory saver).

    Durable HITL requires a checkpointer; ``InMemorySaver`` keeps tests fully
    offline. The wiring task swaps in ``AsyncPostgresSaver`` for production.
    """
    if checkpointer is None:
        checkpointer = InMemorySaver()
    return build_graph().compile(checkpointer=checkpointer)


# Module-level compiled graph (in-memory checkpointer for now).
compiled_graph = compile_graph()
