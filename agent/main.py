import os
import shutil
import tempfile
import uuid
import warnings
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the demo project root (one level up from agent/) BEFORE
# importing src.agent — that import constructs ChatOpenAI at module load,
# which needs OPENAI_API_KEY in the environment already.
_demo_root = Path(__file__).parent.parent
for env_path in (_demo_root / ".env", Path(".env")):
    if env_path.is_file():
        load_dotenv(env_path)
        break
else:
    load_dotenv()

from fastapi import FastAPI, File, UploadFile
import uvicorn
from src.agent import graph
from src.ingest import ingest_document
from copilotkit import LangGraphAGUIAgent
from ag_ui_langgraph import add_langgraph_fastapi_endpoint

app = FastAPI()


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
        chunks = ingest_document(path, document_id)
    finally:
        path.unlink(missing_ok=True)
    return {"document_id": document_id, "chunks": chunks, "filename": file.filename}


add_langgraph_fastapi_endpoint(
    app=app,
    agent=LangGraphAGUIAgent(
        name="sample_agent",
        description="An example agent to use as a starting point for your own agent.",
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
