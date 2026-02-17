"""Pydantic models for API request/response validation."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


# ── Request Models ──────────────────────────────────────────────


class ResearchRequest(BaseModel):
    """Request to start a research task."""

    query: str = Field(..., min_length=3, max_length=2000, description="Research query")
    max_iterations: int = Field(default=3, ge=1, le=10, description="Max refinement iterations")
    thread_id: str | None = Field(default=None, description="Existing thread to append to")


# ── Response Models ─────────────────────────────────────────────


class TaskCreated(BaseModel):
    """Response after a research task is created."""

    task_id: str
    thread_id: str
    thread_item_id: str
    status: str = "started"


class SourceOut(BaseModel):
    """A source in the final report."""

    title: str
    link: str
    snippet: str = ""
    source_type: str = ""
    credibility_score: float = 0.5
    index: int = 0


class ConflictOut(BaseModel):
    """A detected conflict between sources."""

    claim_a: str
    source_a: str
    claim_b: str
    source_b: str
    description: str
    resolution: str = ""


class CritiqueOut(BaseModel):
    """Critique summary."""

    overall_score: float
    gaps: list[str] = []
    diversity_issues: list[str] = []
    suggestions: list[str] = []
    summary: str = ""


class ReportOut(BaseModel):
    """Full research report."""

    id: str
    query: str
    report: str
    sources: list[SourceOut] = []
    conflicts: list[ConflictOut] = []
    critique: CritiqueOut | None = None
    iterations: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HistoryItem(BaseModel):
    """Summary item for the history list."""

    id: str
    query: str
    summary: str = ""
    source_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HistoryList(BaseModel):
    """Paginated history response."""

    items: list[HistoryItem] = []
    total: int = 0


# ── SSE Event Models ────────────────────────────────────────────


class SSEStepEvent(BaseModel):
    """An agent step broadcast over SSE."""

    thread_id: str
    thread_item_id: str
    steps: list[dict] = []


class SSESourceEvent(BaseModel):
    """Sources broadcast over SSE."""

    thread_id: str
    thread_item_id: str
    sources: list[SourceOut] = []


class SSEAnswerEvent(BaseModel):
    """Incremental answer text broadcast over SSE."""

    thread_id: str
    thread_item_id: str
    answer: dict  # {"text": "chunk..."}


class SSEDoneEvent(BaseModel):
    """Terminal event for SSE stream."""

    type: str = "done"
    thread_id: str
    thread_item_id: str
    status: str = "complete"
