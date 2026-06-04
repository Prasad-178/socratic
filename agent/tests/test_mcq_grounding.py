"""Grounding tests for MCQ generation (monkeypatched generate_structured)."""
import src.nodes.quiz as quiz
from langchain_core.documents import Document

from src.nodes.quiz import _GenMCQ, build_mcqs_from_chunks
from src.state import Objective


def _fake_gen(returns: _GenMCQ):
    async def _gen(prompt, schema, **kwargs):
        # Return a copy so each call is independent.
        return _GenMCQ(**returns.model_dump())

    return _gen


async def test_mcqs_are_grounded(monkeypatch):
    monkeypatch.setattr(
        quiz,
        "generate_structured",
        _fake_gen(
            _GenMCQ(
                question="What is the powerhouse of the cell?",
                options=["Mitochondria", "Nucleus", "Ribosome", "Golgi"],
                correct_index=0,
                explanation="Mitochondria produce ATP.",
                hint="Think about energy.",
                source_pages=[3],
            )
        ),
    )
    obj = Objective(
        id="o1", title="Cell biology", description="d", difficulty="beginner",
        key_points=["organelles"],
    )
    chunks = [
        Document(
            page_content="The mitochondria is the powerhouse of the cell.",
            metadata={"page": 3, "document_id": "doc1"},
        )
    ]
    mcqs = await build_mcqs_from_chunks(obj, chunks, n=1)
    m = mcqs[0]
    assert len(m.options) == 4
    assert 0 <= m.correct_index < 4
    assert set(m.source_pages) <= {3}
    assert m.objective_id == "o1"
    assert m.id  # non-empty unique id


async def test_source_pages_constrained_to_provided(monkeypatch):
    # Model hallucinates page 99 which isn't in the provided chunks; it must be dropped.
    monkeypatch.setattr(
        quiz,
        "generate_structured",
        _fake_gen(
            _GenMCQ(
                question="q",
                options=["a", "b", "c", "d"],
                correct_index=1,
                explanation="e",
                hint="h",
                source_pages=[99, 5],
            )
        ),
    )
    obj = Objective(id="o2", title="T", description="d", difficulty="beginner")
    chunks = [
        Document(page_content="x", metadata={"page": 5}),
        Document(page_content="y", metadata={"page": 7}),
    ]
    mcqs = await build_mcqs_from_chunks(obj, chunks, n=1)
    assert set(mcqs[0].source_pages) <= {5, 7}
    assert 99 not in mcqs[0].source_pages


async def test_options_clamped_to_four_and_index_in_range(monkeypatch):
    # Model returns 6 options and an out-of-range correct_index.
    monkeypatch.setattr(
        quiz,
        "generate_structured",
        _fake_gen(
            _GenMCQ(
                question="q",
                options=["a", "b", "c", "d", "e", "f"],
                correct_index=9,
                explanation="e",
                hint="h",
                source_pages=[1],
            )
        ),
    )
    obj = Objective(id="o3", title="T", description="d", difficulty="beginner")
    chunks = [Document(page_content="x", metadata={"page": 1})]
    mcqs = await build_mcqs_from_chunks(obj, chunks, n=2)
    assert len(mcqs) == 2
    for m in mcqs:
        assert len(m.options) == 4
        assert 0 <= m.correct_index < 4
