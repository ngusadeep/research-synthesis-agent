"""Celery app: broker and backend use Redis."""

import os

from celery import Celery

from config import settings

# Apply LangSmith tracing for Celery workers (must run before any LangChain/LangGraph code)
if settings.langsmith_tracing and settings.langsmith_api_key:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_ENDPOINT"] = (
        settings.langsmith_endpoint or ""
    ).strip() or "https://api.smith.langchain.com"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project.strip().strip('"')
    if settings.langsmith_endpoint:
        os.environ["LANGCHAIN_ENDPOINT"] = (settings.langsmith_endpoint or "").strip()
    if settings.langsmith_workspace_id:
        os.environ["LANGSMITH_WORKSPACE_ID"] = (
            settings.langsmith_workspace_id.strip().strip('"')
        )

app = Celery(
    "research_synthesis_agent",
    broker=settings.redis_url or "redis://localhost:6379/0",
    backend=settings.redis_url or "redis://localhost:6379/0",
    include=["worker.tasks"],
)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
