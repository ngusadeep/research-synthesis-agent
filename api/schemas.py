"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000, description="Research query")
    max_iterations: int = Field(default=3, ge=1, le=10, description="Max refinement iterations")
    thread_id: str | None = Field(default=None, description="Existing thread to append to")


class TaskCreated(BaseModel):
    task_id: str
    thread_id: str
    thread_item_id: str
    status: str = "started"


class SourceOut(BaseModel):
    title: str
    link: str
    snippet: str = ""
    source_type: str = ""
    credibility_score: float = 0.5
    index: int = 0


class ConflictOut(BaseModel):
    claim_a: str
    source_a: str
    claim_b: str
    source_b: str
    description: str
    resolution: str = ""


class CritiqueOut(BaseModel):
    overall_score: float
    gaps: list[str] = []
    diversity_issues: list[str] = []
    suggestions: list[str] = []
    summary: str = ""


class ReportOut(BaseModel):
    id: str
    query: str
    report: str
    sources: list[SourceOut] = []
    conflicts: list[ConflictOut] = []
    critique: CritiqueOut | None = None
    iterations: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HistoryItem(BaseModel):
    id: str
    query: str
    summary: str = ""
    source_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HistoryList(BaseModel):
    items: list[HistoryItem] = []
    total: int = 0
