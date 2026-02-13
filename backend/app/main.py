"""FastAPI application entry point for the research agent backend."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router
from app.memory.vector_store import memory_store

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _configure_langsmith() -> None:
    """Set LangSmith env vars so LangChain/LangGraph traces are sent to LangSmith."""
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
    if settings.langsmith_workspace_id:
        os.environ["LANGSMITH_WORKSPACE_ID"] = settings.langsmith_workspace_id
    logger.info("LangSmith tracing enabled (project=%s)", settings.langsmith_project)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and clean up resources."""
    logger.info("Starting Research Agent Backend...")

    # LangSmith tracing (must be set before any LangChain/LangGraph calls)
    _configure_langsmith()

    # Initialize ChromaDB memory store
    memory_store.initialize()
    logger.info("ChromaDB memory store initialized")

    yield

    logger.info("Shutting down Research Agent Backend...")


app = FastAPI(
    title="Research Synthesis Agent API",
    description="Multi-source research synthesizer powered by LangGraph",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the API router
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "research-agent"}
