"""Request schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str = Field(
        ..., min_length=1, max_length=2000, description="User message or research query"
    )
    mode: Literal["research", "quick"] = Field(
        default="research",
        description="research = full multi-source pipeline (with intent detection); quick = simple chat only",
    )
    max_iterations: int = Field(
        default=3, ge=1, le=10, description="Max refinement iterations"
    )
    thread_id: str | None = Field(
        default=None,
        description="Thread/chat ID from the client. Used for the whole session (task meta, SSE, checkpoints).",
    )
    thread_item_id: str | None = Field(
        default=None,
        description="Optional message/item ID from the client so backend echoes it in SSE events.",
    )
