import pytest
from pathlib import Path
from src.ingest import parse_pdf, ingest_document

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


@pytest.mark.integration
def test_parse_pdf_has_page_provenance():
    docs = parse_pdf(FIXTURE)
    assert len(docs) > 0
    assert any(isinstance(d.metadata.get("page"), int) for d in docs)


@pytest.mark.integration
def test_ingest_document_returns_chunk_count():
    n = ingest_document(FIXTURE, "test-doc")
    assert n > 0
