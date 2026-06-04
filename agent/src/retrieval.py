"""Retrieval layer: vector search + FlashRank reranking."""
import warnings

from langchain_classic.retrievers import ContextualCompressionRetriever
from langchain_community.document_compressors import FlashrankRerank
from langchain_core.documents import Document

from src.ingest import _store


def retrieve(
    query: str,
    *,
    document_id: str,
    k: int = 20,
    top_n: int = 5,
) -> list[Document]:
    """Retrieve and rerank chunks relevant to *query* within a single document.

    Args:
        query: Natural-language query (e.g. a learning objective).
        document_id: Filter to chunks that belong to this document.
        k: Number of candidates fetched from pgvector before reranking.
        top_n: Number of chunks to return after FlashRank reranking.

    Returns:
        Up to *top_n* chunks, ordered by relevance.
    """
    # PGVector 0.0.17 accepts a flat dict for equality filters on JSONB metadata
    base = _store().as_retriever(
        search_kwargs={"k": k, "filter": {"document_id": document_id}},
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        compressor = FlashrankRerank(model="ms-marco-MiniLM-L-12-v2", top_n=top_n)
    retriever = ContextualCompressionRetriever(
        base_compressor=compressor,
        base_retriever=base,
    )
    return retriever.invoke(query)
