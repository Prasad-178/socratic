"""Graph state + Pydantic schemas for the Socratic agent.

These names are the contract for every node and test — lock them here and
import them everywhere else.
"""
from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

Difficulty = Literal["beginner", "intermediate", "advanced"]


class Objective(BaseModel):
    """A single learning objective extracted from the document."""

    id: str
    title: str
    description: str
    difficulty: Difficulty
    key_points: list[str] = Field(default_factory=list)
    status: Literal["pending", "in_progress", "done"] = "pending"


class Plan(BaseModel):
    """The full lesson plan: an ordered list of objectives + metadata."""

    objectives: list[Objective]
    overall_difficulty: Difficulty
    summary: str


class MCQ(BaseModel):
    """A grounded multiple-choice question for one objective."""

    id: str
    objective_id: str
    question: str
    options: list[str]  # exactly 4
    correct_index: int
    explanation: str
    hint: str
    source_pages: list[int] = Field(default_factory=list)


class MCQResult(BaseModel):
    """The learner's outcome on a single MCQ."""

    mcq_id: str
    objective_id: str
    chosen_index: int
    correct: bool
    attempts: int


class SocraticState(TypedDict, total=False):
    """Top-level graph state.

    ``results`` accumulates across the quiz loop (operator.add reducer) and
    ``messages`` uses the standard LangGraph message reducer so summary
    messages append rather than overwrite.
    """

    document_id: str
    chunk_texts: list[str]
    plan: Plan | None
    objectives: list[Objective]
    current_objective_idx: int
    current_mcqs: list[MCQ]
    current_mcq_idx: int
    results: Annotated[list[MCQResult], operator.add]
    messages: Annotated[list[AnyMessage], add_messages]
    phase: str
    plan_status: str
    feedback: str | None
