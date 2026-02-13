"""FastAPI routes for the research agent API."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.api.models import (
    ConflictOut,
    CritiqueOut,
    HistoryItem,
    HistoryList,
    ReportOut,
    ResearchRequest,
    SourceOut,
    TaskCreated,
)
from app.agent.graph import create_runnable, get_checkpointer
from app.agent.state import ResearchState
from app.memory.vector_store import memory_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# In-memory task registry for active research tasks
# task_id -> {"queue": asyncio.Queue, "status": str, "result": dict | None}
_tasks: dict[str, dict[str, Any]] = {}

# In-memory report cache (supplements ChromaDB for full report text)
_report_cache: dict[str, dict] = {}


@router.post("/research", response_model=TaskCreated)
async def start_research(request: ResearchRequest) -> TaskCreated:
    """
    Start a new research task.

    Creates a background task that runs the LangGraph agent and streams
    events to a queue that the SSE endpoint reads from.
    """
    task_id = str(uuid4())
    thread_id = request.thread_id or str(uuid4())
    thread_item_id = str(uuid4())

    # Create the event queue for SSE streaming
    queue: asyncio.Queue = asyncio.Queue()
    _tasks[task_id] = {
        "queue": queue,
        "status": "running",
        "result": None,
        "query": request.query,
        "thread_id": thread_id,
        "thread_item_id": thread_item_id,
    }

    # Launch the agent in the background
    asyncio.create_task(
        _run_research_agent(
            task_id=task_id,
            query=request.query,
            thread_id=thread_id,
            thread_item_id=thread_item_id,
            max_iterations=request.max_iterations,
            queue=queue,
        )
    )

    return TaskCreated(
        task_id=task_id,
        thread_id=thread_id,
        thread_item_id=thread_item_id,
        status="started",
    )


@router.get("/research/stream/{task_id}")
async def stream_research(task_id: str, request: Request) -> EventSourceResponse:
    """
    Stream research agent events via Server-Sent Events.

    Event types match what the frontend expects:
    - steps: Agent planning/progress steps
    - sources: Retrieved source documents
    - answer: Incremental report text
    - done: Terminal event
    - error: Error event
    """
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task_info = _tasks[task_id]
    queue: asyncio.Queue = task_info["queue"]
    thread_id = task_info["thread_id"]
    thread_item_id = task_info["thread_item_id"]

    async def event_generator():
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=60.0)
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"event": "ping", "data": "{}"}
                    continue

                if event is None:
                    # Sentinel: stream is done
                    break

                event_type = event.get("type", "unknown")
                event_data = event.get("data", {})

                # Wrap with thread IDs for the frontend
                payload = {
                    "threadId": thread_id,
                    "threadItemId": thread_item_id,
                    **event_data,
                }

                yield {
                    "event": event_type,
                    "data": json.dumps(payload),
                }

                if event_type in ("done", "error"):
                    break

        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for task {task_id}")
        finally:
            # Clean up task after stream ends (keep for a bit for reconnection)
            asyncio.get_event_loop().call_later(300, lambda: _tasks.pop(task_id, None))

    return EventSourceResponse(event_generator())


@router.get("/history", response_model=HistoryList)
async def list_history(limit: int = 50, offset: int = 0) -> HistoryList:
    """List past research reports."""
    items, total = memory_store.list_reports(limit=limit, offset=offset)

    history_items = []
    for item in items:
        meta = item.get("metadata", {})
        history_items.append(HistoryItem(
            id=item["id"],
            query=item.get("query", ""),
            summary=meta.get("query", "")[:200],
            source_count=meta.get("source_count", 0),
            created_at=datetime.fromisoformat(meta["created_at"]) if meta.get("created_at") else datetime.now(timezone.utc),
        ))

    return HistoryList(items=history_items, total=total)


@router.get("/history/{report_id}", response_model=ReportOut)
async def get_report(report_id: str) -> ReportOut:
    """Retrieve a full research report by ID."""
    # Check in-memory cache first
    cached = _report_cache.get(report_id)
    if cached:
        return ReportOut(**cached)

    # Fall back to ChromaDB
    report_data = memory_store.get_report(report_id)
    if not report_data:
        raise HTTPException(status_code=404, detail="Report not found")

    meta = report_data.get("metadata", {})
    return ReportOut(
        id=report_id,
        query=report_data.get("query", ""),
        report=meta.get("report_summary", "Report details not available in storage."),
        created_at=datetime.fromisoformat(meta["created_at"]) if meta.get("created_at") else datetime.now(timezone.utc),
    )


# ── Background agent runner ────────────────────────────────────


async def _run_research_agent(
    task_id: str,
    query: str,
    thread_id: str,
    thread_item_id: str,
    max_iterations: int,
    queue: asyncio.Queue,
) -> None:
    """
    Run the LangGraph research agent and push events to the SSE queue.

    This is the bridge between the LangGraph execution and the SSE stream.
    """
    try:
        # Create event sender that pushes to the SSE queue
        async def send_event(event_type: str, data: dict) -> None:
            await queue.put({"type": event_type, "data": data})

        # Build initial state
        initial_state: dict[str, Any] = {
            "query": query,
            "task_id": task_id,
            "thread_id": thread_id,
            "thread_item_id": thread_item_id,
            "documents": [],
            "plan": [],
            "conflicts": [],
            "draft": "",
            "critique": None,
            "iteration": 0,
            "max_iterations": max_iterations,
            "final_report": "",
            "sources_metadata": [],
            "_send_event": send_event,
        }

        # Create and run the graph
        checkpointer = await get_checkpointer()
        async with checkpointer:
            runnable = await create_runnable(checkpointer)

            config = {"configurable": {"thread_id": thread_id}}
            final_state = await runnable.ainvoke(initial_state, config=config)

        # Extract results
        final_report = final_state.get("final_report", "")
        documents = final_state.get("documents", [])
        conflicts = final_state.get("conflicts", [])
        critique = final_state.get("critique")
        iteration = final_state.get("iteration", 1)

        # Store in memory
        sources_list = [
            {
                "title": doc.title,
                "link": doc.source,
                "snippet": doc.snippet,
                "source_type": doc.source_type,
                "credibility_score": doc.credibility_score,
            }
            for doc in documents
        ]
        conflicts_list = [
            {
                "claim_a": c.claim_a,
                "source_a": c.source_a,
                "claim_b": c.claim_b,
                "source_b": c.source_b,
                "description": c.description,
            }
            for c in conflicts
        ]

        # Store in ChromaDB
        memory_store.store_report(
            report_id=task_id,
            query=query,
            report=final_report,
            sources=sources_list,
            conflicts=conflicts_list,
            critique={"overall_score": critique.overall_score, "summary": critique.summary} if critique else None,
            iterations=iteration,
        )

        # Cache full report
        _report_cache[task_id] = {
            "id": task_id,
            "query": query,
            "report": final_report,
            "sources": [SourceOut(index=i, **s).model_dump() for i, s in enumerate(sources_list)],
            "conflicts": [ConflictOut(**c).model_dump() for c in conflicts_list],
            "critique": CritiqueOut(
                overall_score=critique.overall_score,
                gaps=critique.gaps,
                diversity_issues=critique.diversity_issues,
                suggestions=critique.suggestions,
                summary=critique.summary,
            ).model_dump() if critique else None,
            "iterations": iteration,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Update source credibility
        for doc in documents:
            memory_store.update_credibility(
                url=doc.source,
                title=doc.title,
                source_type=doc.source_type,
                score=doc.credibility_score,
            )

        # Send done event
        await send_event("done", {"type": "done", "status": "complete"})

        _tasks[task_id]["status"] = "completed"
        _tasks[task_id]["result"] = {"report_id": task_id}

    except Exception as e:
        logger.exception(f"Research agent failed for task {task_id}: {e}")
        await queue.put({
            "type": "error",
            "data": {"error": str(e), "type": "agent_error"},
        })
        _tasks[task_id]["status"] = "failed"
    finally:
        # Send sentinel to close the SSE stream
        await queue.put(None)
