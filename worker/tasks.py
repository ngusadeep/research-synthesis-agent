"""Celery task: run research agent and publish events to Redis for SSE."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis

from config import settings
from celery_app import app
from worker.redis_events import (
    META_TTL_SECONDS,
    REDIS_META_KEY_PREFIX,
    REDIS_STREAM_CHANNEL_PREFIX,
)

logger = logging.getLogger(__name__)


def _get_redis():
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL not set")
    return redis.from_url(settings.redis_url, decode_responses=True)


def _publish_event(redis_client: redis.Redis, task_id: str, event_type: str, data: dict) -> None:
    channel = f"{REDIS_STREAM_CHANNEL_PREFIX}{task_id}"
    payload = json.dumps({"type": event_type, "data": data})
    redis_client.publish(channel, payload)


def _set_task_meta(
    redis_client: redis.Redis, task_id: str, thread_id: str, thread_item_id: str
) -> None:
    key = f"{REDIS_META_KEY_PREFIX}{task_id}"
    redis_client.setex(
        key, META_TTL_SECONDS, json.dumps({"thread_id": thread_id, "thread_item_id": thread_item_id})
    )


async def _run_research_async(
    task_id: str,
    query: str,
    thread_id: str,
    thread_item_id: str,
    max_iterations: int,
    redis_client: redis.Redis,
) -> None:
    from core.graph import create_runnable, get_checkpointer
    from memory.vector_store import memory_store

    try:
        memory_store.initialize()
    except RuntimeError:
        pass

    loop = asyncio.get_event_loop()

    def publish(event_type: str, data: dict) -> None:
        _publish_event(redis_client, task_id, event_type, data)

    async def send_event(event_type: str, data: dict) -> None:
        _t, _d = event_type, data
        await loop.run_in_executor(None, lambda: publish(_t, _d))

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

    checkpointer = await get_checkpointer()
    async with checkpointer:
        runnable = await create_runnable(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        final_state = await runnable.ainvoke(initial_state, config=config)

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
        {"claim_a": c.claim_a, "source_a": c.source_a, "claim_b": c.claim_b, "source_b": c.source_b, "description": c.description}
        for c in conflicts
    ]

    memory_store.store_report(
        report_id=task_id,
        query=query,
        report=final_report,
        sources=sources_list,
        conflicts=conflicts_list,
        critique={"overall_score": critique.overall_score, "summary": critique.summary} if critique else None,
        iterations=iteration,
    )

    for doc in documents:
        memory_store.update_credibility(
            url=doc.source, title=doc.title, source_type=doc.source_type, score=doc.credibility_score
        )

    await send_event("done", {"type": "done", "status": "complete"})


@app.task(bind=True, name="worker.run_research")
def run_research_task(
    self,
    task_id: str,
    query: str,
    thread_id: str,
    thread_item_id: str,
    max_iterations: int,
) -> None:
    """Run the research graph in a worker; publish events to Redis for SSE."""
    redis_client = _get_redis()
    _set_task_meta(redis_client, task_id, thread_id, thread_item_id)
    try:
        asyncio.run(
            _run_research_async(
                task_id=task_id,
                query=query,
                thread_id=thread_id,
                thread_item_id=thread_item_id,
                max_iterations=max_iterations,
                redis_client=redis_client,
            )
        )
    except Exception as e:
        logger.exception("Research task %s failed: %s", task_id, e)
        _publish_event(redis_client, task_id, "error", {"error": str(e), "type": "agent_error"})
