"""SerpAPI search tool."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from config import settings

logger = logging.getLogger(__name__)


class SerpApiSearchInput(BaseModel):
    query: str = Field(description="Search query")
    max_results: int = Field(default=5, description="Maximum number of results")


async def _serpapi_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    def _sync_search() -> list[dict[str, Any]]:
        results = []
        try:
            from serpapi import GoogleSearch

            params = {"q": query, "api_key": settings.serpapi_api_key, "num": max_results, "engine": "google"}
            data = GoogleSearch(params).get_dict()
            for item in data.get("organic_results", [])[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "content": item.get("snippet", ""),
                    "source": item.get("link", ""),
                    "source_type": "general",
                    "snippet": item.get("snippet", "")[:300],
                    "metadata": {
                        "position": item.get("position", 0),
                        "displayed_link": item.get("displayed_link", ""),
                        "date": item.get("date", ""),
                    },
                })
        except Exception as e:
            logger.error("SerpAPI search failed: %s", e)
        return results

    return await asyncio.get_event_loop().run_in_executor(None, _sync_search)


serpapi_search = StructuredTool.from_function(
    coroutine=_serpapi_search,
    name="serpapi_search",
    description="Search Google via SerpAPI. Fallback when other sources are insufficient.",
    args_schema=SerpApiSearchInput,
)
