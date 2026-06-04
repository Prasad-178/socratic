"""PDF ingestion pipeline: parse → chunk → embed → store in pgvector."""
from __future__ import annotations

import functools
from pathlib import Path

import psycopg
from langchain_core.documents import Document
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType
from docling.chunking import HybridChunker
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
from docling.document_converter import DocumentConverter, PdfFormatOption
from langchain_postgres import PGVector
from langchain_postgres.vectorstores import DistanceStrategy

from src.settings import settings
from src.llm import get_embeddings

COLLECTION = "socratic_docs"

# ---------------------------------------------------------------------------
# Memoized singletons  (FIX M1 + M6)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _get_embeddings_cached():
    """Return a single shared embeddings instance (loaded once per process)."""
    return get_embeddings()


@functools.lru_cache(maxsize=1)
def _configured_dim() -> int:
    """Return the embedding dimension for the *currently configured* model.

    Probes the embeddings object once and caches the result.  Used to guard
    against mixed-dimension inserts when switching embedding models.
    """
    return len(_get_embeddings_cached().embed_query("dimension probe"))


@functools.lru_cache(maxsize=1)
def _get_converter() -> DocumentConverter:
    """Return a single shared DocumentConverter (Docling models loaded once)."""
    return _make_converter()


@functools.lru_cache(maxsize=1)
def _get_store() -> PGVector:
    """Return a single shared PGVector store instance."""
    return _store_new()


# ---------------------------------------------------------------------------
# Docling converter  (FIX M3)
# ---------------------------------------------------------------------------

_DEVICE_MAP: dict[str, AcceleratorDevice] = {
    "cpu": AcceleratorDevice.CPU,
    "cuda": AcceleratorDevice.CUDA,
    "mps": AcceleratorDevice.MPS,
    "auto": AcceleratorDevice.AUTO,
}


def _make_converter() -> DocumentConverter:
    """Build a DocumentConverter with device/threads from settings.

    Apple MPS (Metal) does not support float64, which the layout model
    (RT-DETRv2) requires.  The default device is CPU to avoid the
    ``Cannot convert a MPS Tensor to float64`` runtime error on macOS.
    Override via ``DOCLING_DEVICE=mps|cuda|auto`` in the environment once
    the upstream model supports it.
    """
    device = _DEVICE_MAP.get(settings.docling_device.lower(), AcceleratorDevice.CPU)
    opts = PdfPipelineOptions()
    opts.accelerator_options = AcceleratorOptions(
        num_threads=settings.docling_num_threads,
        device=device,
    )
    return DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=opts)}
    )


# ---------------------------------------------------------------------------
# Page-provenance helper  (FIX M5 — pure, testable)
# ---------------------------------------------------------------------------

def _extract_page(dl_meta: dict) -> int | None:
    """Return the 1-based page number from a Docling chunk's ``dl_meta`` dict.

    Primary path: ``doc_items[0].prov[0].page_no`` (or ``page``).
    Fallback: walk every doc_item / prov entry for any non-None page.
    Returns ``None`` when no provenance data is present or parseable.
    """
    page_no: int | None = None
    try:
        prov = dl_meta["doc_items"][0]["prov"][0]
        raw = prov.get("page_no") or prov.get("page")
        if raw is not None:
            page_no = int(raw)
    except (KeyError, IndexError, TypeError, ValueError):
        pass

    if page_no is None:
        for item in dl_meta.get("doc_items", []):
            for p in item.get("prov", []):
                raw = p.get("page_no") or p.get("page")
                if raw is not None:
                    try:
                        page_no = int(raw)
                        break
                    except (TypeError, ValueError):
                        pass
            if page_no is not None:
                break

    return page_no


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------

def parse_pdf(path: Path) -> list[Document]:
    """Load and chunk a PDF using Docling with HybridChunker.

    Extracts page-number provenance from the Docling metadata so each
    Document chunk carries ``metadata["page"]`` as an integer (1-based).
    Reuses the cached DocumentConverter (FIX M1/M6).
    """
    loader = DoclingLoader(
        file_path=str(path),
        converter=_get_converter(),
        export_type=ExportType.DOC_CHUNKS,
        chunker=HybridChunker(),
    )
    docs = loader.load()

    for d in docs:
        meta = d.metadata.get("dl_meta", {})
        d.metadata["page"] = _extract_page(meta)
        d.metadata["headings"] = meta.get("headings", [])

    return docs


# ---------------------------------------------------------------------------
# PGVector store factory (internal; public callers use _get_store())
# ---------------------------------------------------------------------------

def _store_new() -> PGVector:
    """Construct a PGVector store using the cached embeddings singleton."""
    return PGVector(
        embeddings=_get_embeddings_cached(),
        collection_name=COLLECTION,
        connection=settings.database_url,
        distance_strategy=DistanceStrategy.COSINE,
        use_jsonb=True,
    )


# Keep the old name used by retrieval.py as a thin shim that returns the
# cached singleton so both callers share one store object.
def _store() -> PGVector:
    return _get_store()


# ---------------------------------------------------------------------------
# HNSW index management  (FIX I1 + M2)
# ---------------------------------------------------------------------------

def ensure_hnsw_index() -> None:
    """Create an HNSW index on the embedding column if it doesn't exist.

    Uses the *configured* embedding dimension (from the probed embeddings
    object) rather than inferring it from an arbitrary on-disk row — this
    prevents silent dimension mismatches when switching embedding models.

    Raises RuntimeError if existing rows were embedded with a different
    dimension than the currently configured model.
    """
    configured = _configured_dim()
    # psycopg 3 DSN uses plain postgresql:// driver prefix
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, autocommit=True) as conn:
        # Check whether the HNSW index already exists
        row = conn.execute(
            "SELECT 1 FROM pg_indexes "
            "WHERE tablename = 'langchain_pg_embedding' "
            "AND indexname = 'langchain_pg_embedding_hnsw_idx';"
        ).fetchone()
        if row:
            return  # index already exists; nothing to do

        # Read the on-disk dimension using vector_dims()  (FIX M2)
        dim_row = conn.execute(
            "SELECT vector_dims(embedding) "
            "FROM langchain_pg_embedding LIMIT 1;"
        ).fetchone()

        if dim_row is None or dim_row[0] is None:
            # No rows yet — use configured dim; index will be created on next call
            # after rows are inserted, OR proceed with ALTER now to lock in the dim.
            pass
        else:
            disk_dim = dim_row[0]
            if disk_dim != configured:
                raise RuntimeError(
                    f"Embedding dimension mismatch: rows on disk have dimension "
                    f"{disk_dim} but the configured embedding model produces "
                    f"{configured} dimensions. The embedding model changed. "
                    f"Reset the vector store (docker compose down -v) or use a "
                    f"separate database per embedding model."
                )

        # ALTER the column to the configured dimension so HNSW can be created
        conn.execute(
            f"ALTER TABLE langchain_pg_embedding "
            f"ALTER COLUMN embedding TYPE vector({configured}) "
            f"USING embedding::vector({configured});"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS langchain_pg_embedding_hnsw_idx "
            "ON langchain_pg_embedding USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 200);"
        )


# ---------------------------------------------------------------------------
# Pre-insert dimension guard  (FIX I1 — fast pre-check)
# ---------------------------------------------------------------------------

def _check_dimension_before_insert() -> None:
    """Raise RuntimeError if existing on-disk rows clash with the configured dim.

    Called before inserting new documents so the error is surfaced immediately
    rather than letting pgvector fail with a cryptic cast error.
    """
    configured = _configured_dim()
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn) as conn:
        dim_row = conn.execute(
            "SELECT vector_dims(embedding) "
            "FROM langchain_pg_embedding LIMIT 1;"
        ).fetchone()
    if dim_row is not None and dim_row[0] is not None:
        disk_dim = dim_row[0]
        if disk_dim != configured:
            raise RuntimeError(
                f"Embedding dimension mismatch: rows on disk have dimension "
                f"{disk_dim} but the configured embedding model produces "
                f"{configured} dimensions. The embedding model changed. "
                f"Reset the vector store (docker compose down -v) or use a "
                f"separate database per embedding model."
            )


# ---------------------------------------------------------------------------
# Public ingestion entry-point
# ---------------------------------------------------------------------------

def ingest_document(path: Path, document_id: str) -> int:
    """Parse a PDF, tag every chunk with ``document_id``, embed and store them.

    Returns the number of chunks ingested.
    NOTE: this function is intentionally synchronous (single-user POC); callers
    in async contexts must wrap it with ``run_in_threadpool``.
    """
    _check_dimension_before_insert()
    docs = parse_pdf(path)
    for d in docs:
        d.metadata["document_id"] = document_id
    _get_store().add_documents(docs)
    ensure_hnsw_index()
    return len(docs)
