# CLAUDE.md

Guidance for AI coding agents (and humans) working in this repository.

## What this is

**Socratic** turns a PDF into a structured, interactive lesson:

1. **Upload** a PDF → it's parsed and embedded.
2. **Plan** — the agent proposes learning objectives + difficulty (a todo list).
3. **Approve** — a Human-in-the-Loop (HITL) interrupt; you review/edit/regenerate the plan before anything else happens.
4. **Quiz** — per objective, grounded multiple-choice questions render in a custom widget. Correct → green + explanation + continue; incorrect → red + hint + retry (no penalty).
5. **Tutor** — ask for hints/explanations; the tutor is structurally prevented from revealing the answer and steers you back to the lesson.
6. **Summary** — progress report + personalized study tips.

## Architecture (3 services, ONE Postgres)

```
web/  Next.js 16 + CopilotKit v2   ──AG-UI(HTTP)──▶  agent/  FastAPI + LangGraph
  (uploader, plan/MCQ widgets,        /api/copilotkit      (custom StateGraph,
   tutor panel)                       POST /upload,         interrupt-based HITL)
                                      POST /tutor                  │
                                                                   ▼
                                            Postgres + pgvector (pg16)
                                            • LangGraph checkpointer (durable HITL)
                                            • pgvector embeddings (RAG)
```

The same Postgres holds **both** the LangGraph checkpoint tables (durable interrupts, survive restart) and the pgvector embedding store.

## Repo layout

```
agent/                 Python FastAPI + LangGraph (uv-managed, Python ≥3.12)
  src/
    main.py            FastAPI app: AG-UI endpoint (mounts graph), POST /upload, POST /tutor, GET /health
    graph.py           build_graph() / compile_graph(checkpointer) — wires the nodes; AsyncPostgresSaver at runtime
    state.py           SocraticState (TypedDict) + Pydantic schemas (Objective, Plan, MCQ, MCQResult)
    nodes/plan.py      Send map-reduce planning + LLM consolidation into ≤6 objectives
    nodes/quiz.py      grounded MCQ generation + the interrupt-based quiz loop
    nodes/summarize.py progress report + study tips
    ingest.py          Docling parse (page provenance) → pgvector → HNSW index
    retrieval.py       top-20 → FlashRank rerank → top-5
    tutor.py           guardrailed Socratic tutor + answer-leak check
    llm.py             OpenRouter chat (+ fallback) / embeddings / structured-output-with-retry
    settings.py        pydantic-settings (reads agent/.env)
  scripts/             live_smoke.py (real-model e2e), capture_interrupt.py (AG-UI event inspector)
  tests/               pytest; fast offline tests + @pytest.mark.integration (need DB + models)
web/                   Next.js + CopilotKit v2 (npm)
  src/app/             layout.tsx (CopilotKit provider), page.tsx (lesson flow), api/{copilotkit,upload,tutor}/
  src/components/      Uploader, PlanApproval, McqWidget, Summary, Tutor
samples/               ready-to-use test PDFs (medical, CS, finance, astronomy) + generator
docker-compose.yml     db (pgvector) + agent + web
```

## Setup & run

Prereqs: **Docker**, **[uv](https://docs.astral.sh/uv/)**, **Node 20+**.

```bash
# 1. Keys (only OpenRouter is required)
cp agent/.env.example agent/.env
#   set OPENROUTER_API_KEY=sk-or-...   (LANGSMITH_API_KEY optional; leave LANGSMITH_TRACING=false if unset)

# 2. Database
docker compose up -d db                 # pgvector/pgvector:pg16 on :5432

# 3. Agent  (terminal 1)  — first run downloads ~1GB Docling models (one-time)
cd agent && uv sync && PYTHONPATH=. uv run uvicorn main:app --port 8123

# 4. Web    (terminal 2)
cd web && npm install && npm run dev     # http://localhost:3000
```

Then open http://localhost:3000, drop a PDF from `samples/`, and walk: plan → approve → quiz → summary.

## How to test

```bash
cd agent

# Fast, offline, no keys/DB needed (graph logic, grounding, guardrail, interrupt/resume):
uv run pytest -m "not integration" -q

# Integration (needs `docker compose up -d db`; uses real embeddings/models):
uv run pytest -m integration -q

# Full agent e2e with REAL OpenRouter calls (ingest a sample → plan → MCQs → summary → guardrail):
PYTHONPATH=. uv run python scripts/live_smoke.py ../samples/cs_tcp_udp.pdf

# Inspect the exact AG-UI interrupt event the frontend receives:
PYTHONPATH=. uv run python scripts/capture_interrupt.py

# Frontend typecheck + build:
cd ../web && npx tsc --noEmit && npm run build
```

Lint: `cd agent && uv run ruff check src/`.

## Key things an agent should know (gotchas)

- **Interrupt payload is a JSON string.** The `ag-ui-langgraph` bridge emits LangGraph `interrupt()` values as a JSON *string* (`event.value`), not an object. The frontend `JSON.parse`s it before reading `.type`. Don't "simplify" that away.
- **Two interrupt types, one mechanism.** `{type:"plan_approval", plan:[...]}` and `{type:"mcq", mcq:{...}}`, both via `interrupt()` / resumed with `Command(resume=...)`. Resume payloads: plan `{action, plan, feedback}`; mcq `{chosen_index, correct, attempts}`. Keep these byte-for-byte in sync between `agent/src/nodes` and `web/src/components`.
- **Graph state stores JSON-native dicts**, not Pydantic instances (msgpack-clean for the durable Postgres checkpointer). Nodes re-validate with `Model(**d)` where they need typed access.
- **Durable persistence:** `AsyncPostgresSaver` is built in the FastAPI lifespan (it pins to the running event loop, so it can't be constructed at import). Interrupts survive an agent restart.
- **RAG:** Docling forces CPU on Apple Silicon (MPS float64 crash) via `settings.docling_device`. The pgvector column is dimensioned on first ingest; **switching embedding models requires a fresh DB** (`docker compose down -v`) — there's a guard that raises a clear error otherwise.
- **MCQs:** 2 per objective by default (`generate_mcqs_node`, `n=2`); objectives are capped at 6 in `nodes/plan.py` (`MAX_OBJECTIVES`). Users trim objectives in the plan UI to shorten the lesson.
- **The tutor is a separate `/tutor` endpoint** (not the graph), with a structural answer-leak check. It never sees the quiz graph's suspended state.
- **LLM via OpenRouter only** (no OpenAI key). Default model `openai/gpt-4o-mini`; structured output uses `method="function_calling"` + a Pydantic-ValidationError retry.

## Common tasks

- **Change number of MCQs:** `generate_mcqs_node(..., n=2)` in `agent/src/nodes/quiz.py`.
- **Change max objectives:** `MAX_OBJECTIVES` in `agent/src/nodes/plan.py`.
- **Swap the LLM/embedding model:** `OPENROUTER_MODEL` / `EMBED_MODEL` in `agent/.env` (then `docker compose down -v` if embedding dims change).
- **Add a new graph node:** add to `agent/src/nodes/`, wire in `build_graph()` (`agent/src/graph.py`) with `destinations=` hints, add an offline test under `agent/tests/` using `GenericFakeChatModel`-style stubs + `InMemorySaver`.
- **Tune the tutor guardrail:** `agent/src/tutor.py` (`SYSTEM` prompt + `leaks_answer`).

## Conventions

- Run agent commands from `agent/` with `uv run`; tests are deterministic offline (`-m "not integration"`) — keep them that way (monkeypatch `generate_structured` / `retrieve`).
- Don't commit `agent/.env` (gitignored). `samples/*.pdf` are committed test fixtures.
- The design spec + implementation plan live under `docs/superpowers/` (gitignored, local working notes).
