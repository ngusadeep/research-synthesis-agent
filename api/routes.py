"""Research API routes and SSE streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from api.schemas import (
    ConflictOut,
    CritiqueOut,
    HistoryItem,
    HistoryList,
    ReportOut,
    ResearchRequest,
    SourceOut,
    TaskCreated,
)
from config import settings
from core.graph import create_runnable, get_checkpointer
from core.intent import classify_research_vs_chat
from core.simple_chat import run_simple_chat_and_send
from core.state import set_send_event
from memory.vector_store import memory_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_tasks: dict[str, dict[str, Any]] = {}
_report_cache: dict[str, dict] = {}


def _use_celery() -> bool:
    return bool(settings.redis_url)


@router.post("/research", response_model=TaskCreated)
async def start_research(request: ResearchRequest) -> TaskCreated:
    """Start a research task. Use client-provided thread_id so the session is tied to that chat/thread."""
    task_id = str(uuid4())
    thread_id = request.thread_id or str(uuid4())
    thread_item_id = request.thread_item_id or str(uuid4())

    if _use_celery():
        from worker.tasks import run_research_task

        run_research_task.delay(
            task_id=task_id,
            query=request.query,
            thread_id=thread_id,
            thread_item_id=thread_item_id,
            max_iterations=request.max_iterations,
            mode=request.mode,
        )
        return TaskCreated(
            task_id=task_id,
            thread_id=thread_id,
            thread_item_id=thread_item_id,
            status="started",
        )

    queue: asyncio.Queue = asyncio.Queue()
    _tasks[task_id] = {
        "queue": queue,
        "status": "running",
        "result": None,
        "query": request.query,
        "thread_id": thread_id,
        "thread_item_id": thread_item_id,
    }
    asyncio.create_task(
        _run_research_agent(
            task_id=task_id,
            query=request.query,
            thread_id=thread_id,
            thread_item_id=thread_item_id,
            max_iterations=request.max_iterations,
            mode=request.mode,
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
    if _use_celery():
        return EventSourceResponse(
            _stream_from_redis(task_id, request),
            headers={"Cache-Control": "no-store"},
        )

    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task_info = _tasks[task_id]
    queue: asyncio.Queue = task_info["queue"]
    thread_id = task_info["thread_id"]
    thread_item_id = task_info["thread_item_id"]

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=60.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if event is None:
                    break
                event_type = event.get("type", "unknown")
                event_data = event.get("data", {})
                payload = {
                    "threadId": thread_id,
                    "threadItemId": thread_item_id,
                    **event_data,
                }
                yield {"event": event_type, "data": json.dumps(payload)}
                if event_type in ("done", "error"):
                    break
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled for task %s", task_id)
        finally:
            asyncio.get_event_loop().call_later(300, lambda: _tasks.pop(task_id, None))

    return EventSourceResponse(event_generator())


async def _stream_from_redis(task_id: str, request: Request):
    from worker.redis_events import REDIS_META_KEY_PREFIX, REDIS_STREAM_CHANNEL_PREFIX

    redis_client = await __get_async_redis()
    meta_key = f"{REDIS_META_KEY_PREFIX}{task_id}"
    channel = f"{REDIS_STREAM_CHANNEL_PREFIX}{task_id}"

    for _ in range(50):
        meta_raw = await redis_client.get(meta_key)
        if meta_raw:
            break
        await asyncio.sleep(0.2)
    else:
        yield {
            "event": "error",
            "data": json.dumps({"error": "Task not found or not started"}),
        }
        return

    try:
        meta = json.loads(meta_raw)
        thread_id = meta.get("thread_id", "")
        thread_item_id = meta.get("thread_item_id", "")
    except (json.JSONDecodeError, TypeError):
        thread_id = thread_item_id = ""

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    last_ping = asyncio.get_event_loop().time()
    try:
        while True:
            if await request.is_disconnected():
                break
            msg = await pubsub.get_message(ignore_subscribe_messages=True)
            if msg is not None:
                try:
                    data = (
                        json.loads(msg["data"])
                        if isinstance(msg["data"], str)
                        else msg["data"]
                    )
                except (json.JSONDecodeError, TypeError):
                    continue
                event_type = data.get("type", "unknown")
                event_data = data.get("data", {})
                payload = {
                    "threadId": thread_id,
                    "threadItemId": thread_item_id,
                    **event_data,
                }
                yield {"event": event_type, "data": json.dumps(payload)}
                if event_type in ("done", "error"):
                    break
            else:
                now = asyncio.get_event_loop().time()
                if now - last_ping >= 60.0:
                    yield {"event": "ping", "data": "{}"}
                    last_ping = now
            await asyncio.sleep(0.25)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for task %s", task_id)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


async def __get_async_redis():
    from redis.asyncio import from_url

    return from_url(settings.redis_url, decode_responses=True)


@router.get("/history", response_model=HistoryList)
async def list_history(limit: int = 50, offset: int = 0) -> HistoryList:
    items, total = memory_store.list_reports(limit=limit, offset=offset)
    history_items = []
    for item in items:
        meta = item.get("metadata", {})
        history_items.append(
            HistoryItem(
                id=item["id"],
                query=item.get("query", ""),
                summary=meta.get("query", "")[:200],
                source_count=meta.get("source_count", 0),
                created_at=(
                    datetime.fromisoformat(meta["created_at"])
                    if meta.get("created_at")
                    else datetime.now(timezone.utc)
                ),
            )
        )
    return HistoryList(items=history_items, total=total)


@router.get("/history/{report_id}", response_model=ReportOut)
async def get_report(report_id: str) -> ReportOut:
    if not _use_celery() and report_id in _report_cache:
        return ReportOut(**_report_cache[report_id])
    report_data = memory_store.get_report(report_id)
    if not report_data:
        raise HTTPException(status_code=404, detail="Report not found")
    meta = report_data.get("metadata", {})
    return ReportOut(
        id=report_id,
        query=report_data.get("query", ""),
        report=meta.get("report_summary", "Report details not available in storage."),
        created_at=(
            datetime.fromisoformat(meta["created_at"])
            if meta.get("created_at")
            else datetime.now(timezone.utc)
        ),
    )


async def _run_research_agent(
    task_id: str,
    query: str,
    thread_id: str,
    thread_item_id: str,
    max_iterations: int,
    mode: str,
    queue: asyncio.Queue,
) -> None:
    try:

        async def send_event(event_type: str, data: dict) -> None:
            await queue.put({"type": event_type, "data": data})

        # Quick mode = always simple chat. Research mode = intent check then chat or full pipeline.
        if mode == "quick":
            await run_simple_chat_and_send(query, send_event)
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["result"] = {"report_id": task_id}
            await queue.put(None)
            return
        if mode == "research":
            intent = await classify_research_vs_chat(query)
            if intent == "chat":
                await run_simple_chat_and_send(query, send_event)
                _tasks[task_id]["status"] = "completed"
                _tasks[task_id]["result"] = {"report_id": task_id}
                await queue.put(None)
                return

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
        }

        checkpointer_cm = await get_checkpointer()
        async with checkpointer_cm as checkpointer:
            await checkpointer.setup()
            runnable = await create_runnable(checkpointer)
            config = {"configurable": {"thread_id": thread_id}}
            set_send_event(send_event)
            try:
                final_state = await runnable.ainvoke(initial_state, config=config)
            finally:
                set_send_event(None)

        final_report = final_state.get("final_report", "")
        documents = final_state.get("documents", [])
        conflicts = final_state.get("conflicts", [])
        critique = final_state.get("critique")
        iteration = final_state.get("iteration", 1)

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

        memory_store.store_report(
            report_id=task_id,
            query=query,
            report=final_report,
            sources=sources_list,
            conflicts=conflicts_list,
            critique=(
                {"overall_score": critique.overall_score, "summary": critique.summary}
                if critique
                else None
            ),
            iterations=iteration,
        )

        _report_cache[task_id] = {
            "id": task_id,
            "query": query,
            "report": final_report,
            "sources": [
                SourceOut(index=i, **s).model_dump() for i, s in enumerate(sources_list)
            ],
            "conflicts": [ConflictOut(**c).model_dump() for c in conflicts_list],
            "critique": (
                CritiqueOut(
                    overall_score=critique.overall_score,
                    gaps=critique.gaps,
                    diversity_issues=critique.diversity_issues,
                    suggestions=critique.suggestions,
                    summary=critique.summary,
                ).model_dump()
                if critique
                else None
            ),
            "iterations": iteration,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        for doc in documents:
            memory_store.update_credibility(
                url=doc.source,
                title=doc.title,
                source_type=doc.source_type,
                score=doc.credibility_score,
            )

        await send_event("done", {"type": "done", "status": "complete"})
        _tasks[task_id]["status"] = "completed"
        _tasks[task_id]["result"] = {"report_id": task_id}

    except Exception as e:
        logger.exception("Research agent failed for task %s: %s", task_id, e)
        await queue.put(
            {"type": "error", "data": {"error": str(e), "type": "agent_error"}}
        )
        _tasks[task_id]["status"] = "failed"
    finally:
        await queue.put(None)
