import os
import shutil
import tempfile
import uuid
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the demo project root (one level up from agent/) BEFORE
# importing application modules so pydantic settings pick it up. The imports
# below therefore intentionally follow this call (E402 is expected/suppressed).
_demo_root = Path(__file__).parent.parent
for env_path in (_demo_root / ".env", Path(".env")):
    if env_path.is_file():
        load_dotenv(env_path)
        break
else:
    load_dotenv()

import uvicorn  # noqa: E402
from ag_ui_langgraph import add_langgraph_fastapi_endpoint  # noqa: E402
from copilotkit import LangGraphAGUIAgent  # noqa: E402
from fastapi import FastAPI, File, UploadFile  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from psycopg_pool import AsyncConnectionPool  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from src.graph import compile_graph  # noqa: E402
from src.ingest import ingest_document  # noqa: E402
from src.settings import settings  # noqa: E402
from src.tutor import tutor_answer  # noqa: E402

# ---------------------------------------------------------------------------
# Durable persistence: AsyncPostgresSaver over a psycopg async pool.
#
# Wiring constraints that shape this module:
#   * add_langgraph_fastapi_endpoint / LangGraphAGUIAgent need the compiled
#     graph OBJECT at registration time (module scope).
#   * AsyncPostgresSaver.__init__ calls asyncio.get_running_loop() and pins the
#     saver to that loop, so it can only be constructed inside a running loop
#     (i.e. NOT at bare module import, which would raise "no running event
#     loop" and break a plain `import main`).
#
# Resolution: at module scope we compile the graph with a throwaway in-memory
# checkpointer so the AG-UI agent can register against a stable graph object.
# Inside the FastAPI lifespan (running on uvicorn's serving loop) we open the
# pool, build the AsyncPostgresSaver there, run setup(), and rebind it onto the
# already-registered graph via ``graph.checkpointer = saver``. The AG-UI agent
# holds a reference to this same graph object, so every request thereafter uses
# the durable Postgres saver — bound to the correct serving loop.
# ---------------------------------------------------------------------------

# SQLAlchemy-style dsn (postgresql+psycopg://) -> plain libpq dsn for psycopg.
_dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")

# Pool construction needs no event loop (open=False); safe at module scope.
pool = AsyncConnectionPool(
    conninfo=_dsn,
    open=False,
    kwargs={
        # Mirror what langgraph's from_conn_string sets internally:
        "autocommit": True,  # setup() migrations / writes commit immediately
        "prepare_threshold": 0,  # avoid prepared-statement reuse across the pool
        "row_factory": dict_row,  # the saver expects dict rows
    },
)

# Compiled at import time so the agent can register; the in-memory checkpointer
# is a placeholder that is replaced with the durable saver in the lifespan.
graph = compile_graph()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Running inside uvicorn's event loop: open the pool, build + bind the
    # durable saver (loop-pinned here), and ensure checkpoint tables exist.
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()  # idempotent: creates checkpoint tables/migrations
    graph.checkpointer = saver
    try:
        yield
    finally:
        await pool.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """Ingest a PDF document into the vector store.

    Returns a unique ``document_id`` that downstream endpoints (MCQ generation,
    retrieval) use to scope queries to this document.
    """
    document_id = uuid.uuid4().hex
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        path = Path(tmp.name)
    try:
        # Single-user POC: run synchronous ingestion in a thread so the event
        # loop is not blocked during Docling parsing and embedding calls.
        chunks = await run_in_threadpool(ingest_document, path, document_id)
    finally:
        path.unlink(missing_ok=True)
    return {"document_id": document_id, "chunks": chunks, "filename": file.filename}


class TutorReq(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    user_message: str


@app.post("/tutor")
async def tutor(req: TutorReq):
    """Return a Socratic hint for the MCQ the learner is currently working on.

    The reply is guaranteed never to contain the correct option text; the
    structural guardrail in ``src.tutor`` rewrites any leaking model output.
    """
    return {"reply": await tutor_answer(**req.model_dump())}


# Mount the Socratic tutor graph as an AG-UI agent at the server root.
add_langgraph_fastapi_endpoint(
    app=app,
    agent=LangGraphAGUIAgent(
        name="socratic",
        description="PDF->interactive lesson tutor",
        graph=graph,
    ),
    path="/",
)


def main():
    """Run the uvicorn server."""
    port = int(os.getenv("PORT", "8123"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )


warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
if __name__ == "__main__":
    main()
