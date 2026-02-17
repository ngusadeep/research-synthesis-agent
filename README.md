# Multi-Source Research Synthesizer (Agentic RAG)

## Overview

Autonomous research agent: given a query, it plans sub-queries across ArXiv, Tavily, Wikipedia, and SerpAPI, synthesizes a cited report, detects conflicts, self-critiques, and refines until satisfied. Results stream in real time to a chat UI. Config: `config/config.yml` for defaults, `.env` for secrets and URLs.

## Features

- **Multi-source search** — ArXiv, Tavily, Wikipedia, SerpAPI with dynamic source selection
- **Query expansion** — Planner produces 3–5 focused sub-queries per iteration
- **Conflict detection** — Synthesizer highlights contradictions across sources
- **Self-critique loop** — Critic scores quality; loops back to Planner if score &lt; 0.7
- **Long-term memory** — ChromaDB for past reports and source credibility
- **Real-time streaming** — SSE for steps, sources, and report text
- **Checkpointing** — Postgres for recoverable LangGraph state
- **Distributed mode** — Optional Celery + Redis for high concurrency

## Workflow

User submits a query → Frontend starts a task and opens an SSE stream. Planner generates sub-queries → Workers search in parallel → Synthesizer builds a cited report and detects conflicts → Critic scores the report; if below threshold, loop back to Planner with feedback. When done, the report is stored in ChromaDB and streamed to the client.

## Tech Stack

| Layer     | Technology                                  |
| --------- | ------------------------------------------- |
| Frontend  | Next.js 14, TypeScript, Tailwind, shadcn/ui |
| Backend   | FastAPI, LangGraph, LangChain, OpenAI       |
| Search    | Tavily, ArXiv, Wikipedia, SerpAPI           |
| Storage   | ChromaDB, Postgres, Redis, Dexie (frontend) |
| Tasks     | Celery (optional)                           |
| Streaming | SSE (sse-starlette)                         |

## Author

Samwel Ngusa
