"""Global state schema for the graph (single source of truth)."""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, TypedDict


@dataclass
class SubQuery:
    """Planner output: one sub-query with source hint."""

    query: str
    source_type: str  # "academic" | "news" | "reference" | "general"
    rationale: str = ""


@dataclass
class RetrievedDocument:
    """Worker output: one retrieved document with metadata."""

    title: str
    content: str
    source: str
    source_type: str
    snippet: str = ""
    credibility_score: float = 0.5
    metadata: dict = field(default_factory=dict)


@dataclass
class Conflict:
    """Synthesizer output: detected contradiction between sources."""

    claim_a: str
    source_a: str
    claim_b: str
    source_b: str
    description: str
    resolution: str = ""


@dataclass
class SourceMeta:
    """Metadata for credibility tracking (long-term memory)."""

    url: str
    title: str
    source_type: str
    credibility_score: float = 0.5


@dataclass
class Critique:
    """Critic output: quality score and refinement decision."""

    needs_refinement: bool
    overall_score: float
    gaps: list[str] = field(default_factory=list)
    diversity_issues: list[str] = field(default_factory=list)
    outdated_concerns: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    summary: str = ""


class ResearchState(TypedDict, total=False):
    """
    Global state object. Orchestrator routes this between agents.
    Append-only reducers allow parallel workers to merge results.
    """

    query: str
    task_id: str
    thread_id: str
    thread_item_id: str
    plan: list[SubQuery]
    documents: Annotated[list[RetrievedDocument], operator.add]
    draft: str
    conflicts: list[Conflict]
    sources_metadata: list[SourceMeta]
    critique: Critique | None
    iteration: int
    max_iterations: int
    final_report: str
    _send_event: object
