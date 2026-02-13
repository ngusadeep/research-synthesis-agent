"""Tavily web search tool for current events and general web content."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)


class TavilySearchInput(BaseModel):
    """Input schema for Tavily search."""

    query: str = Field(description="Search query for web content")
    max_results: int = Field(default=5, description="Maximum number of results")
    search_depth: str = Field(default="advanced", description="Search depth: basic or advanced")


async def _tavily_search(
    query: str, max_results: int = 5, search_depth: str = "advanced"
) -> list[dict[str, Any]]:
    """
    Search the web using Tavily API.

    Tavily is optimized for LLM-friendly results with clean content extraction.
    """
    try:
        from tavily import AsyncTavilyClient

        client = AsyncTavilyClient(api_key=settings.tavily_api_key)
        response = await client.search(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            include_raw_content=False,
        )

        results = []
        for item in response.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "source": item.get("url", ""),
                "source_type": "news",
                "snippet": item.get("content", "")[:300],
                "metadata": {
                    "score": item.get("score", 0),
                    "published_date": item.get("published_date", ""),
                },
            })
        return results

    except Exception as e:
        logger.error(f"Tavily search failed: {e}")
        return []


tavily_search = StructuredTool.from_function(
    coroutine=_tavily_search,
    name="tavily_search",
    description="Search the web for current events, news, and general information. Best for recent developments and real-time data.",
    args_schema=TavilySearchInput,
)
