"""PDF ingestion pipeline: parse → chunk → embed → store in pgvector."""
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


def _make_converter() -> DocumentConverter:
    """Build a DocumentConverter that always runs on CPU.

    Apple MPS (Metal) does not support float64, which the layout model
    (RT-DETRv2) requires.  Explicitly selecting CPU prevents the
    ``Cannot convert a MPS Tensor to float64`` runtime error on macOS.
    """
    opts = PdfPipelineOptions()
    opts.accelerator_options = AcceleratorOptions(
        num_threads=4,
        device=AcceleratorDevice.CPU,
    )
    return DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=opts)}
    )


def parse_pdf(path: Path) -> list[Document]:
    """Load and chunk a PDF using Docling with HybridChunker.

    Extracts page-number provenance from the Docling metadata so each
    Document chunk carries ``metadata["page"]`` as an integer (1-based).
    """
    loader = DoclingLoader(
        file_path=str(path),
        converter=_make_converter(),
        export_type=ExportType.DOC_CHUNKS,
        chunker=HybridChunker(),
    )
    docs = loader.load()

    for d in docs:
        # Docling 2.x stores provenance in dl_meta.doc_items[0].prov[0].page_no
        meta = d.metadata.get("dl_meta", {})
        page_no = None
        try:
            # Prefer the first provenance entry from the first doc_item
            prov = meta["doc_items"][0]["prov"][0]
            raw = prov.get("page_no") or prov.get("page")
            if raw is not None:
                page_no = int(raw)
        except (KeyError, IndexError, TypeError, ValueError):
            pass

        if page_no is None:
            # Fallback: walk all doc_items looking for any page_no
            for item in meta.get("doc_items", []):
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

        d.metadata["page"] = page_no
        d.metadata["headings"] = meta.get("headings", [])

    return docs


def _store() -> PGVector:
    """Return a PGVector store using the configured database and embeddings."""
    return PGVector(
        embeddings=get_embeddings(),
        collection_name=COLLECTION,
        connection=settings.database_url,
        distance_strategy=DistanceStrategy.COSINE,
        use_jsonb=True,
    )


def ensure_hnsw_index() -> None:
    """Create an HNSW index on the embedding column if it doesn't exist.

    Must be called after ``add_documents`` so the table already exists.
    pgvector HNSW requires a *dimensioned* vector column (vector(N)).  If the
    column is untyped (PGVector creates it without dimensions on the first
    insert) we infer the dimension from existing rows and ALTER the column
    before indexing.  fastembed (384) and text-embedding-3-large (1536) are
    both within pgvector's 2000-dim HNSW limit.
    """
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
            return  # nothing to do

        # Infer dimension from an existing embedding row
        dim_row = conn.execute(
            "SELECT array_length(embedding::real[], 1) "
            "FROM langchain_pg_embedding LIMIT 1;"
        ).fetchone()
        if dim_row is None or dim_row[0] is None:
            return  # no rows yet; index will be created on next call

        dim = dim_row[0]

        # Cast the column to vector(dim) so HNSW can operate on it
        conn.execute(
            f"ALTER TABLE langchain_pg_embedding "
            f"ALTER COLUMN embedding TYPE vector({dim}) "
            f"USING embedding::vector({dim});"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS langchain_pg_embedding_hnsw_idx "
            "ON langchain_pg_embedding USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 200);"
        )


def ingest_document(path: Path, document_id: str) -> int:
    """Parse a PDF, tag every chunk with ``document_id``, embed and store them.

    Returns the number of chunks ingested.
    """
    docs = parse_pdf(path)
    for d in docs:
        d.metadata["document_id"] = document_id
    _store().add_documents(docs)
    ensure_hnsw_index()
    return len(docs)
