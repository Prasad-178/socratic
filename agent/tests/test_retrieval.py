import pytest
from src.ingest import ingest_document
from src.retrieval import retrieve
from pathlib import Path


@pytest.mark.integration
def test_retrieve_returns_ranked_chunks():
    ingest_document(Path(__file__).parent / "fixtures" / "sample.pdf", "ret-doc")
    docs = retrieve("the main topic", document_id="ret-doc", top_n=5)
    assert 1 <= len(docs) <= 5
    assert all("page" in d.metadata for d in docs)
