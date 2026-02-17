# Multi-Source Research Synthesizer (Agentic RAG)

An autonomous research agent that takes a user query, plans sub-queries across multiple sources (ArXiv, Tavily, Wikipedia, SerpAPI), synthesizes a cited report, detects conflicts, self-critiques, and iteratively refines the output — all streamed in real-time to a modern chat UI.

## Project structure (backend)

Backend at repo root (production-grade multi-agent layout):

- **Root**: `main.py` (FastAPI app)
- **`config/`** — settings (Pydantic, `.env`): `settings.py`
- **`core/`** — orchestration and state: `state.py` (global state schema), `graph.py` (LangGraph + Postgres checkpointer)
- **`agents/`** — specialized nodes: planner, worker, synthesizer, critic
- **`tools/`** — schema-validated tools: arxiv, tavily, wikipedia, serpapi
- **`memory/`** — long-term semantic memory (ChromaDB: reports, source credibility)
- **`api/`** — routes (`routes.py`), schemas (`schemas/` request & response), models (`models/`)
- **`worker/`** — Celery app (`celery_app.py`) and tasks (`tasks.py`); runs research graph, publishes SSE via Redis)

**Modes:**
- **Single-process** (no `REDIS_URL`): API runs the graph in-process; fine for low concurrency.
- **Distributed** (`REDIS_URL` set): API enqueues work to Celery; workers run the graph and publish to Redis; API streams from Redis. Handles many concurrent requests without crashing.

Run (single-process): `uv run uvicorn main:app --reload --port 8000`

## Architecture

```
Next.js UI (port 3000)
    ↓  POST /api/research → { task_id }
    ↓  GET  /api/research/stream/{task_id}  (SSE)
FastAPI Backend (port 8000)
    ↓  (if REDIS_URL) enqueue → Redis → Celery worker(s)
    ↓  (else) asyncio.create_task in-process
LangGraph StateGraph
    Planner → Worker(s) → Synthesizer → Critic
       ↑___________________________|  (loop if needs refinement)
    ↓
ChromaDB (reports + source credibility)
Postgres (graph checkpoints)
Redis    (broker + SSE pub/sub when distributed)
```

## Features

- **Dynamic Source Selection** — ArXiv (academic), Tavily (news), Wikipedia (reference), SerpAPI (general)
- **Iterative Query Expansion** — Planner generates 3-5 focused sub-queries per iteration
- **Conflict Detection** — Synthesizer identifies contradictions between sources
- **Self-Critique Loop** — Critic evaluates gaps, diversity, and outdated info; loops back if score < 0.7
- **Long-Term Memory** — ChromaDB persists past reports and tracks source credibility over time
- **Real-Time Streaming** — SSE delivers agent steps, sources, and report text as they're produced
- **Graph Checkpointing** — Postgres checkpointer for recoverable state

## Tech Stack

| Layer      | Technology                                                     |
| ---------- | -------------------------------------------------------------- |
| Frontend   | Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui  |
| Backend    | FastAPI, LangGraph, LangChain, OpenAI GPT-4o-mini             |
| Search     | Tavily, ArXiv, Wikipedia, SerpAPI                              |
| Storage    | ChromaDB (vector memory), Postgres (checkpoints), Redis (broker + pub/sub), Dexie (local) |
| Tasks      | Celery (optional; use when `REDIS_URL` is set for distributed load)                      |
| Streaming  | Server-Sent Events (SSE via sse-starlette)                                               |

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 18+ and npm (or bun)
- API keys: OpenAI, Tavily, SerpAPI (see below)

### 1. Backend (from repo root)

Requires Postgres (for graph checkpoints). Create a DB and set `DATABASE_URL` in `.env`.

```bash
cp .env.example .env
# Edit .env: OPENAI_API_KEY, TAVILY_API_KEY, SERPAPI_API_KEY, DATABASE_URL (e.g. postgresql://postgres:postgres@localhost:5432/research)

uv sync
uv run uvicorn main:app --reload --port 8000
```

The backend will be available at `http://localhost:8000`. Check health at `http://localhost:8000/health`.

### 2. Frontend

```bash
cd frontend

# Copy environment config
cp .env.local.example .env.local

# Install dependencies
npm install --legacy-peer-deps

# Start dev server
npm run dev
```

The frontend will be available at `http://localhost:3000`.

### 3. Distributed mode (Celery + Redis) — many concurrent requests

With many frontend threads/requests, run Redis and Celery so the API stays responsive and workers process research in the background:

```bash
# Terminal 1: Redis
docker run -p 6379:6379 redis:7-alpine

# Terminal 2: API (with REDIS_URL in .env)
export REDIS_URL=redis://localhost:6379/0
uv run uvicorn main:app --reload --port 8000

# Terminal 3: Celery worker
export REDIS_URL=redis://localhost:6379/0
uv run celery -A celery_app worker --loglevel=info --concurrency=4
```

Set `REDIS_URL=redis://localhost:6379/0` in `.env` so the API and worker use it. The API will enqueue research tasks; the worker runs the graph and publishes events to Redis; the API streams those events over SSE.

### 4. Docker Compose (deployment)

Runs API, Celery worker, and Redis together. Use this for deployment or to avoid running multiple terminals.

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY, TAVILY_API_KEY, SERPAPI_API_KEY (and REDIS_URL is set by compose)

docker compose up --build
```

- **Nginx**: `http://localhost` (port 80) — reverse proxy: `/api` → API, `/` → frontend
- API (direct): `http://localhost:8000`
- Frontend (direct): `http://localhost:3000`
- Redis: internal 6379; Postgres: internal 5432
- Celery worker: 4 concurrent tasks (set in `docker-compose.yml`)

Data: ChromaDB/SQLite in `app_data`, Postgres in `postgres_data`. Scale workers: `docker compose up -d --scale celery_worker=2`.

## Environment Variables

### Backend (`.env` at project root)

| Variable                 | Required | Default        | Description                  |
| ------------------------ | -------- | -------------- | ---------------------------- |
| `OPENAI_API_KEY`         | Yes      | —              | OpenAI API key               |
| `TAVILY_API_KEY`         | Yes      | —              | Tavily search API key        |
| `SERPAPI_API_KEY`        | No       | —              | SerpAPI key (fallback search)|
| `CHROMA_PERSIST_DIRECTORY` | No     | `./chroma_db`  | ChromaDB storage path        |
| `DATABASE_URL`            | Yes*   | —              | Postgres URL for graph checkpoints (e.g. `postgresql://postgres:postgres@localhost:5432/research`). |
| `REDIS_URL`               | No     | —              | Redis URL for Celery + SSE (e.g. `redis://localhost:6379/0`). When set, research runs in workers. |
| `OPENAI_MODEL`           | No       | `gpt-4o-mini`  | OpenAI model to use          |
| `LANGSMITH_TRACING`      | No       | `false`        | Enable LangSmith tracing     |
| `LANGSMITH_API_KEY`      | No*      | —              | LangSmith API key (*if tracing on) |
| `LANGSMITH_PROJECT`     | No       | `research-synthesis-agent` | LangSmith project name |
| `LANGSMITH_WORKSPACE_ID`| No       | —              | Optional; for multi-workspace keys |

### LangSmith (observability)

To trace agent runs (LangGraph, LLM calls, tools) in [LangSmith](https://smith.langchain.com):

1. Get an API key at [smith.langchain.com](https://smith.langchain.com).
2. In `.env` at project root set:
   - `LANGSMITH_TRACING=true`
   - `LANGSMITH_API_KEY=lsv2_pt_...`
   - `LANGSMITH_PROJECT=research-synthesis-agent` (optional; default above)
3. Restart the backend. Each research run will appear as a trace in your LangSmith project with nested spans for planner, worker, synthesizer, and critic.

### Frontend (`frontend/.env.local`)

| Variable              | Default                 | Description               |
| --------------------- | ----------------------- | ------------------------- |
| `NEXT_PUBLIC_API_URL`  | `http://localhost:8000` | FastAPI backend URL       |

## API Endpoints

| Method | Endpoint                          | Description                       |
| ------ | --------------------------------- | --------------------------------- |
| POST   | `/api/research`                   | Start a research task             |
| GET    | `/api/research/stream/{task_id}`  | SSE stream of agent events        |
| GET    | `/api/history`                    | List past research reports        |
| GET    | `/api/history/{id}`               | Get a full report by ID           |
| GET    | `/health`                         | Health check                      |

### SSE Event Types

| Event      | Description                                      |
| ---------- | ------------------------------------------------ |
| `steps`    | Agent planning/progress steps with status         |
| `sources`  | Retrieved source documents                        |
| `answer`   | Incremental report text (markdown)                |
| `done`     | Terminal event — research complete                |
| `error`    | Error event with details                          |

## Project Structure

```
research-synthesis-agent/
├── main.py                      # FastAPI app entry (uvicorn main:app)
├── config.py                    # Pydantic Settings from .env
├── agent/                       # LangGraph agent
│   ├── graph.py                 # StateGraph wiring
│   ├── state.py                 # ResearchState TypedDict
│   ├── nodes/
│   │   ├── planner.py           # Query planning & sub-query generation
│   │   ├── worker.py            # Parallel source retrieval
│   │   ├── synthesizer.py       # Report synthesis & conflict detection
│   │   └── critic.py            # Self-critique & loop control
│   └── tools/
│       ├── arxiv.py             # ArXiv academic search
│       ├── tavily.py            # Tavily web search
│       ├── wikipedia.py         # Wikipedia reference search
│       └── serpapi.py           # SerpAPI fallback search
├── memory/
│   └── vector_store.py          # ChromaDB: reports + credibility
├── api/
│   ├── routes.py                # FastAPI endpoints & SSE streaming
│   └── models.py                # Pydantic request/response models
├── frontend/                    # Next.js (unchanged)
│   ├── app/                     # Next.js App Router pages
│   ├── components/              # React components (shadcn/ui based)
│   ├── hooks/
│   │   └── agent-provider.tsx   # SSE client & agent flow
│   ├── lib/config/
│   │   └── chat-mode.ts         # Research + Quick modes
│   ├── store/                   # Zustand + Dexie state
│   └── .env.local.example
├── pyproject.toml               # Python deps (backend)
├── .env.example                 # Backend env template
└── README.md
```

## How It Works

1. **User submits a query** via the chat UI
2. **Frontend POSTs** to `/api/research` and receives a `task_id`
3. **Frontend connects** to `/api/research/stream/{task_id}` via SSE
4. **Planner** analyzes the query and generates 3-5 sub-queries with source type hints
5. **Workers** execute searches in parallel across ArXiv, Tavily, Wikipedia, and SerpAPI
6. **Synthesizer** merges all documents into a structured markdown report with citations and conflict detection
7. **Critic** evaluates the report for gaps, diversity, and quality
8. If the score is below 0.7 and iterations remain, the **Critic loops back to Planner** with feedback
9. Once satisfied, the **final report** is stored in ChromaDB and streamed to the frontend
10. **Source credibility** is tracked over time across research sessions

## License

MIT
