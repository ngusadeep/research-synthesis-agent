"""Request schemas."""

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000, description="Research query")
    max_iterations: int = Field(
        default=3, ge=1, le=10, description="Max refinement iterations"
    )
    thread_id: str | None = Field(
        default=None, description="Existing thread to append to"
    )
