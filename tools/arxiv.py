"""ArXiv search tool."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import arxiv
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ArxivSearchInput(BaseModel):
    query: str = Field(description="Search query for academic papers")
    max_results: int = Field(
        default=5, description="Maximum number of results to return"
    )


async def _arxiv_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    def _sync_search() -> list[dict[str, Any]]:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance
        )
        results = []
        try:
            for paper in client.results(search):
                results.append(
                    {
                        "title": paper.title,
                        "content": paper.summary,
                        "source": paper.entry_id,
                        "source_type": "academic",
                        "snippet": paper.summary[:300],
                        "metadata": {
                            "authors": [a.name for a in paper.authors[:5]],
                            "published": (
                                paper.published.isoformat() if paper.published else ""
                            ),
                            "categories": paper.categories,
                            "pdf_url": paper.pdf_url or "",
                        },
                    }
                )
        except Exception as e:
            logger.error("ArXiv search failed: %s", e)
        return results

    return await asyncio.get_event_loop().run_in_executor(None, _sync_search)


arxiv_search = StructuredTool.from_function(
    coroutine=_arxiv_search,
    name="arxiv_search",
    description="Search ArXiv for academic and scientific papers.",
    args_schema=ArxivSearchInput,
)
