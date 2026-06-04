# Architecture

A deep dive into how **Socratic** turns a PDF into a structured, interactive lesson. This document explains the system end-to-end: the services, the agent graph, the human-in-the-loop mechanism, the RAG pipeline, persistence, and the frontend.

---

## 1. Overview

Socratic is a three-service application backed by a single Postgres database:

- **`web/`** — a Next.js + CopilotKit v2 frontend (the guided lesson UI).
- **`agent/`** — a FastAPI service exposing a LangGraph agent over the **AG-UI** protocol, plus two plain HTTP endpoints (`/upload`, `/tutor`).
- **Postgres + pgvector** — does double duty: durable LangGraph checkpoints **and** the RAG vector store.

The pedagogical flow: **upload → plan → approve (HITL) → quiz (per topic) → summary**, with a Socratic tutor that gives hints but never reveals the answer.

---

## 2. Design goals

| Goal | How it's met |
|---|---|
| Structured, persistent pedagogy | A deterministic LangGraph state machine, not a free-form chat |
| Genuine human-in-the-loop | Real LangGraph `interrupt()` + durable Postgres checkpointer (survives restarts) |
| Grounded questions (no hallucinated trivia) | RAG over the PDF with page-level provenance; MCQs cite source pages |
| Scales beyond toy PDFs | Map-reduce planning + per-topic retrieval; nothing holds the whole book in context |
| The "never leak the answer" guarantee | A structural leak-check, not prompt-trust |
| Approachable for non-technical users | Single-column guided flow, plain language, tunable settings in a modal |

---

## 3. System architecture

```mermaid
flowchart LR
    subgraph Browser["🌐 Browser — web/ (Next.js 16 + CopilotKit v2)"]
        UI["Lesson UI<br/>Uploader · Plan · Quiz · Tutor · Summary"]
        Proxy["Next route handlers<br/>/api/upload · /api/tutor · /api/copilotkit"]
    end

    subgraph Agent["⚙️ agent/ — FastAPI (uvicorn, Python 3.12)"]
        AGUI["AG-UI endpoint  (POST /)<br/>ag-ui-langgraph bridge"]
        Upload["POST /upload  (ingest)"]
        Tutor["POST /tutor  (guardrailed)"]
        Graph["LangGraph StateGraph<br/>(plan → HITL → quiz → summary)"]
        RAG["RAG: Docling · pgvector · FlashRank"]
    end

    subgraph DB["🗄️ Postgres 16 + pgvector ≥0.8"]
        CP["checkpoints*  (LangGraph HITL state)"]
        VEC["langchain_pg_embedding  (HNSW vectors)"]
    end

    UI -- "useAgent / useInterrupt<br/>(AG-UI over HTTP)" --> Proxy
    Proxy -- "AG-UI run / resume" --> AGUI
    UI -- "upload PDF" --> Proxy --> Upload
    UI -- "ask for a hint" --> Proxy --> Tutor
    AGUI --> Graph
    Graph -- "interrupt()/resume" --> CP
    Upload --> RAG --> VEC
    Graph -- "retrieve per topic" --> VEC
```

**Why one Postgres for both roles?** The LangGraph checkpointer (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`) and the pgvector store (`langchain_pg_embedding`, `langchain_pg_collection`) use disjoint tables. Sharing one instance removes an entire service from the deployment while keeping the two concerns isolated.

---

## 4. End-to-end flow

```mermaid
sequenceDiagram
    actor U as User
    participant W as web/ (CopilotKit)
    participant A as agent/ (FastAPI)
    participant G as LangGraph
    participant DB as Postgres+pgvector

    U->>W: Upload PDF
    W->>A: POST /api/upload
    A->>A: Docling parse → chunk → embed
    A->>DB: store vectors + HNSW index
    A-->>W: { document_id, chunks }
    W->>A: runAgent(state={document_id, settings})
    A->>G: invoke graph
    G->>DB: load chunks for document_id
    G->>G: map-reduce → consolidate topics (LLM)
    G-->>W: interrupt(plan_approval)  ⟶ rendered as the plan card
    U->>W: edit / Approve
    W->>A: resume(Command(resume={action:"approve", plan}))
    loop for each topic, each question
        G->>DB: retrieve + rerank chunks
        G->>G: generate grounded MCQ (LLM)
        G-->>W: interrupt(mcq)  ⟶ rendered as the question widget
        U->>W: answer (retry on wrong, no penalty)
        opt user asks for a hint
            W->>A: POST /api/tutor (current question)
            A-->>W: Socratic hint (answer never leaked)
        end
        W->>A: resume(Command(resume={chosen_index, correct, attempts}))
    end
    G->>G: summarize (score + study tips)
    G-->>W: phase = "done"  ⟶ Summary
```

Every `interrupt()` durably checkpoints to Postgres, so the flow can resume after an agent restart.

---

## 5. The agent graph (LangGraph)

A **custom `StateGraph`** — the flow is deterministic (not LLM-routed), so explicit nodes/edges map naturally to it. `interrupt()` is a first-class citizen.

```mermaid
flowchart TD
    START((START)) --> RE{route_entry<br/>plan exists?}
    RE -- no --> PLAN[plan<br/>map-reduce subgraph]
    RE -- yes --> APR

    subgraph SUB["plan subgraph (Send map-reduce)"]
        LC[load_chunks] --> FO{{fan out:<br/>Send per chunk}}
        FO --> AC[analyze_chunk ×N<br/>extract candidate topics]
        AC --> RED[reduce<br/>LLM consolidate → ≤ max_objectives]
    end
    PLAN --> APR[approve_plan]

    APR -- "interrupt(plan_approval)" --> APR
    APR -- approve --> SEL{select_objective<br/>topics left?}
    APR -- regenerate --> PLAN

    SEL -- yes --> GEN[generate_mcqs<br/>retrieve + rerank + generate]
    SEL -- no --> SUM[summarize<br/>score + study tips]
    GEN --> ASK[ask_mcq]
    ASK -- "interrupt(mcq)" --> ASK
    ASK -- more questions --> ASK
    ASK -- topic done --> SEL
    SUM --> END((END))
```

### Node responsibilities

| Node | File | What it does |
|---|---|---|
| `route_entry` | `graph.py` | Skip planning if a plan is already in state |
| `plan` | `graph.py` → `nodes/plan.py` | Runs the map-reduce subgraph, writes the consolidated `plan` |
| `load_chunks` | `nodes/plan.py` | Loads the document's chunk texts from pgvector (capped) |
| `analyze_chunk` | `nodes/plan.py` | One `Send` per chunk; extracts 1–2 candidate topics in parallel |
| `reduce` | `nodes/plan.py` | **LLM consolidation** of overlapping candidates → ≤ `max_objectives` distinct topics |
| `approve_plan` | `graph.py` | `interrupt(plan_approval)`; routes on approve/regenerate |
| `select_objective` | `nodes/quiz.py` | Next topic, or → summarize when exhausted |
| `generate_mcqs` | `nodes/quiz.py` | Retrieve + rerank chunks → generate `questions_per_objective` grounded MCQs |
| `ask_mcq` | `nodes/quiz.py` | `interrupt(mcq)` per question; records the outcome; loops |
| `summarize` | `nodes/summarize.py` | Progress report + personalized study tips |

### Why map-reduce for planning

A long PDF can't fit in one prompt. The `Send` API fans out one analysis call per chunk (in parallel), accumulates candidate topics via an `operator.add` reducer, then a single **consolidation** call merges semantic duplicates into a clean, capped set ordered foundational → advanced. This is what lets Socratic handle book-length documents rather than toy PDFs.

---

## 6. Human-in-the-loop: how interrupts actually work

Both the plan approval and every quiz question use the **same** mechanism — LangGraph `interrupt()` — discriminated by a `type` field. This unifies the HITL story and makes the whole flow drivable/testable offline.

```mermaid
sequenceDiagram
    participant G as LangGraph node
    participant B as ag-ui-langgraph bridge
    participant CK as CopilotKit (useInterrupt)
    participant UI as React widget

    G->>G: value = interrupt(payload)
    Note over G: graph SUSPENDS here
    G->>B: pending interrupt
    B->>CK: AG-UI CUSTOM event "on_interrupt"<br/>value = JSON STRING
    CK->>UI: enabled(event) then render(event)
    Note over UI: JSON.parse(event.value) → object<br/>(the value is a STRING — must parse)
    UI->>UI: user interacts (edit plan / answer)
    UI->>CK: resolve(payload)
    CK->>B: forwardedProps.command.resume = payload
    B->>G: Command(resume=payload)
    Note over G: graph RESUMES; interrupt() returns the payload
```

**Two gotchas baked into the implementation:**

1. **The interrupt value is a JSON _string_.** The `ag-ui-langgraph` bridge serializes `interrupt.value` with `dump_json_safe`, so the frontend receives `event.value` as a string. The widgets `JSON.parse` it (`web/src/lib/utils.ts → parseInterruptValue`) before reading `.type`. (Skipping this silently breaks rendering.)
2. **Nodes re-run top-to-bottom on resume.** So `interrupt()` is the first meaningful statement in `approve_plan_node` / `ask_mcq_node`, and everything before it is idempotent state reads — no double side effects.

**The two contracts (kept byte-for-byte across `agent/src/nodes` ↔ `web/src/components`):**

| Interrupt | Agent → UI payload | UI → agent (resume) |
|---|---|---|
| Plan | `{type:"plan_approval", plan:[Objective…]}` | `{action:"approve"\|"regenerate", plan:[…], feedback}` |
| Quiz | `{type:"mcq", mcq:{question, options, correct_index, explanation, hint, source_pages, …}}` | `{chosen_index, correct, attempts}` |

The MCQ retry loop (wrong → red + hint → try again) runs **entirely client-side**; `resolve()` is only called once the question is finished, so the graph stays cleanly suspended on a single pending interrupt the whole time.

---

## 7. RAG pipeline

### Ingestion (`/upload`, runs out-of-band so heavy I/O never blocks the agent loop)

```mermaid
flowchart LR
    PDF[PDF] --> D[Docling parse<br/>HybridChunker]
    D --> P["chunks + page provenance<br/>(dl_meta → page_no)"]
    P --> E["embed<br/>OpenRouter text-embedding-3-large @1536<br/>(fastembed bge-small fallback)"]
    E --> S[(pgvector<br/>langchain_pg_embedding)]
    S --> H["ALTER column → vector(dim)<br/>CREATE HNSW index (cosine)"]
```

- **Docling** is chosen for parsing because it carries `page_no` + section headings into each chunk's metadata — that provenance becomes the MCQ's source-page citation.
- The pgvector column is created un-dimensioned by LangChain, so ingestion dimensions it (`ALTER … vector(N)`) and builds the **HNSW** index (`m=16, ef_construction=200`, cosine) once. A guard raises a clear error if you switch embedding models against a populated DB (different dimension).
- On Apple Silicon, Docling is pinned to CPU (`settings.docling_device`) to dodge an MPS float64 crash; configurable for CUDA hosts.

### Retrieval (per topic, at quiz time)

```mermaid
flowchart LR
    Q["query = topic title + key points"] --> K["pgvector similarity<br/>top-20 (filtered by document_id)"]
    K --> R["FlashRank rerank<br/>ms-marco-MiniLM-L-12-v2"]
    R --> T["top-5 chunks → MCQ generation prompt"]
```

"Retrieve broadly, rank precisely" — 20 candidates reranked down to the 5 most relevant. The reranker is local and free (no extra API key). MCQ generation is constrained to cite only the provided chunks' pages, so questions stay grounded.

---

## 8. State model & persistence

### `SocraticState` (the graph's working memory)

Stored as **JSON-native dicts**, not Pydantic instances. This keeps the LangGraph msgpack checkpoint clean (no "unregistered type" warnings on a durable Postgres round-trip) and keeps state serializable for the AG-UI wire format. Nodes re-validate with `Model(**d)` at the boundary where they need typed access.

```mermaid
classDiagram
    class SocraticState {
        +str document_id
        +list chunk_texts
        +int max_objectives
        +int questions_per_objective
        +dict plan
        +list objectives
        +int current_objective_idx
        +list current_mcqs
        +int current_mcq_idx
        +list results
        +list messages
        +str phase
    }
    class Objective {
        +str id
        +str title
        +str description
        +str difficulty
        +list key_points
        +str status
    }
    class MCQ {
        +str id
        +str objective_id
        +str question
        +list options
        +int correct_index
        +str explanation
        +str hint
        +list source_pages
    }
    class MCQResult {
        +str mcq_id
        +str objective_id
        +int chosen_index
        +bool correct
        +int attempts
    }
    SocraticState --> Objective
    SocraticState --> MCQ
    SocraticState --> MCQResult
```

> `max_objectives` (default 6) and `questions_per_objective` (default 2) are the UI-tunable settings. `results` uses an `operator.add` reducer (accumulates across the quiz) and `messages` uses the LangGraph `add_messages` reducer. `options` is always exactly 4.

### Durable checkpointer

`AsyncPostgresSaver` is built in the FastAPI **lifespan** (it pins to the running event loop, so it can't be constructed at import). It's attached to the compiled graph at startup; `interrupt()`/resume reads and writes the thread's checkpoint, so the lesson survives an agent restart.

---

## 9. LLM / provider layer (`llm.py`)

```mermaid
flowchart TD
    GS["generate_structured(prompt, schema)"] --> M["ChatOpenAI → OpenRouter<br/>(primary model)"]
    M -- "with_fallbacks" --> M2["secondary OpenRouter model"]
    GS --> V{Pydantic valid?}
    V -- no --> RT["re-prompt with the error<br/>(bounded retries)"]
    RT --> M
    V -- yes --> OUT[typed result]
    EMB["get_embeddings()"] --> OR["OpenRouter embeddings"]
    OR -- "no key" --> FE["local fastembed (offline)"]
```

- **OpenRouter only** (no OpenAI key). Default chat `openai/gpt-4o-mini`, with a secondary OpenRouter model as fallback.
- Structured output uses `with_structured_output(method="function_calling")` for the widest model compatibility, wrapped in a **Pydantic-ValidationError retry loop** (the agent's structured calls are why the internal LLM tool-calls exist — they're suppressed in the UI).
- Embeddings via OpenRouter with a local **fastembed** fallback so it runs offline / key-free.

---

## 10. The Socratic tutor & guardrail (`tutor.py`, `/tutor`)

A **separate endpoint**, not part of the quiz graph — so it never touches the suspended graph state and is independently testable.

```mermaid
flowchart LR
    REQ["/tutor {question, options, correct_index, user_message}"] --> SYS["Socratic system prompt<br/>(hints only, steer back)"]
    SYS --> LLM[LLM reply]
    LLM --> LEAK{leaks_answer?<br/>word-boundary match on correct option}
    LEAK -- yes --> RW["refuse + rewrite<br/>(safe hint)"]
    LEAK -- no --> PASS[reply]
```

The guardrail is **structural**: even if the model tries to reveal the answer, `leaks_answer()` detects the correct option's text and replaces the response with a safe hint. This is covered by a unit test that monkeypatches the model to deliberately leak.

---

## 11. Frontend architecture (`web/`)

CopilotKit v2 over the **AG-UI** protocol. The frontend keeps the CopilotKit provider for `useAgent` (kickoff + shared state) and `useInterrupt` (the HITL widgets), but **renders its own UI** — there is no `CopilotChat` surface (it would render the agent's internal tool-calls as JSON).

```mermaid
flowchart TD
    Prov["<CopilotKit> provider"] --> Page[page.tsx — single-column guided flow]
    Page --> Step[Stepper: Upload · Plan · Quiz · Results]
    Page --> Up[Uploader → /api/upload, then setState+runAgent]
    Page --> Set[LessonSettings modal ⚙<br/>questions/topic · #topics]
    Page --> PA["PlanApproval<br/>useInterrupt(plan_approval, renderInChat:false)"]
    Page --> MC["McqWidget<br/>useInterrupt(mcq, renderInChat:false)"]
    MC --> Tut[Tutor panel → /api/tutor]
    Page --> Sum["Summary (reads useAgent state)"]
    Up -- "max_objectives, questions_per_objective" --> Prov
```

- **`renderInChat: false`** → `useInterrupt` returns the element, and the page places it in the active-step area (not in a chat). This is what moved the widgets into a clean lesson panel.
- The Next route handlers (`/api/upload`, `/api/tutor`) proxy to the Python service server-side to avoid browser CORS.
- Motion follows Emil Kowalski's craft principles: custom `ease-out` curve, sub-300ms UI transitions, staggered card entrances, press-scale on buttons, `prefers-reduced-motion` support.

---

## 12. Configuration & tunables

| Setting | Where | Default | Surfaced in UI |
|---|---|---|---|
| Questions per topic | `questions_per_objective` (state) | 2 | ⚙ modal (1–5) |
| Number of topics | `max_objectives` (state) | 6 | ⚙ modal (3–8) |
| Chat model | `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | env |
| Embedding model | `EMBED_MODEL` / `EMBED_DIMENSIONS` | `text-embedding-3-large` / 1536 | env |
| Tracing | `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` | off | env |
| Docling device | `settings.docling_device` | `cpu` | env |

The two lesson tunables flow from the ⚙ modal → React context → `agent.setState()` at kickoff → graph state → `plan.py` (cap) and `quiz.py` (count).

---

## 13. Testing strategy

```mermaid
flowchart LR
    U["Offline unit/e2e<br/>pytest -m 'not integration'"] --> U1["fake LLMs (no key)<br/>InMemorySaver<br/>plan, grounding, summary, guardrail, interrupt/resume"]
    I["Integration<br/>pytest -m integration"] --> I1["real DB + models<br/>ingest, retrieval, durable HITL"]
    L["Live smoke<br/>scripts/live_smoke.py"] --> L1["real OpenRouter<br/>full flow end-to-end"]
    C["capture_interrupt.py"] --> C1["inspect the exact AG-UI interrupt event"]
```

The bulk of the suite is **fast and offline** (monkeypatched `generate_structured`/`retrieve`, `InMemorySaver`), so the graph logic, grounding constraints, the answer-leak guardrail, and interrupt/resume are all verified without keys or a DB.

---

## 14. Key technology decisions

| Concern | Choice | Why |
|---|---|---|
| Agent framework | LangGraph custom `StateGraph` | Deterministic flow; first-class `interrupt()` |
| Frontend ↔ agent | CopilotKit v2 + AG-UI (`LangGraphHttpAgent`) | Streaming state + interrupt widgets; HTTP bridge to FastAPI |
| PDF parsing | Docling `HybridChunker` | Page/heading provenance for citations |
| Vector store | pgvector (HNSW, cosine) | Same Postgres as the checkpointer; no extra service |
| Reranker | FlashRank (local) | Highest-ROI retrieval upgrade, zero cost/key |
| LLM/embeddings | OpenRouter (+ fastembed fallback) | Single key, provider-agnostic, offline-capable |
| Checkpointer | `AsyncPostgresSaver` | Durable `interrupt()`/resume |
| Structured output | `with_structured_output` + Pydantic retry | Reliable schemas across heterogeneous models |
| Guardrail | structural leak-check | Beats prompt-trust; unit-tested |

---

## 15. Running it

See **`CLAUDE.md`** for the full quickstart and test commands. In short:

```bash
cp agent/.env.example agent/.env     # set OPENROUTER_API_KEY
docker compose up -d db              # Postgres + pgvector
cd agent && PYTHONPATH=. uv run uvicorn main:app --port 8123
cd web   && npm run dev              # http://localhost:3000
```

Deliberate non-goals (documented for honesty): multi-user auth, OCR for scanned PDFs, a managed reranker, a background ingestion queue, and anti-cheat server-side grading — each is a conscious scope cut with a clear path to add later.
