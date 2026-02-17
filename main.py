"""FastAPI app entry point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from config import settings
from memory.vector_store import memory_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _configure_langsmith() -> None:
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint.strip()
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project.strip().strip('"')
    if settings.langsmith_endpoint:
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint.strip()
    if settings.langsmith_workspace_id:
        os.environ["LANGSMITH_WORKSPACE_ID"] = (
            settings.langsmith_workspace_id.strip().strip('"')
        )
    logger.info(
        "LangSmith tracing enabled (project=%s, endpoint=%s)",
        settings.langsmith_project,
        settings.langsmith_endpoint or "default",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Research Synthesis Agent API...")
    _configure_langsmith()
    memory_store.initialize()
    logger.info("ChromaDB memory store initialized")
    yield
    logger.info("Shutting down Research Synthesis Agent API...")


app = FastAPI(
    title="Research Synthesis Agent API",
    description="Production-grade multi-agent research synthesizer (LangGraph)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "research-synthesis-agent"}
