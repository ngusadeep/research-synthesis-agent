"""Wikipedia search tool."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import wikipedia
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WikipediaSearchInput(BaseModel):
    query: str = Field(description="Search query for Wikipedia articles")
    max_results: int = Field(default=3, description="Maximum number of results")


async def _wikipedia_search(query: str, max_results: int = 3) -> list[dict[str, Any]]:
    def _sync_search() -> list[dict[str, Any]]:
        results = []
        try:
            titles = wikipedia.search(query, results=max_results)
            for title in titles:
                try:
                    page = wikipedia.page(title, auto_suggest=False)
                    content = page.content[:2000]
                    results.append({
                        "title": page.title,
                        "content": content,
                        "source": page.url,
                        "source_type": "reference",
                        "snippet": page.summary[:300],
                        "metadata": {
                            "page_id": page.pageid,
                            "categories": page.categories[:10] if page.categories else [],
                            "references_count": len(page.references) if page.references else 0,
                        },
                    })
                except (wikipedia.DisambiguationError, wikipedia.PageError) as e:
                    logger.warning("Wikipedia page error for %r: %s", title, e)
        except Exception as e:
            logger.error("Wikipedia search failed: %s", e)
        return results

    return await asyncio.get_event_loop().run_in_executor(None, _sync_search)


wikipedia_search = StructuredTool.from_function(
    coroutine=_wikipedia_search,
    name="wikipedia_search",
    description="Search Wikipedia for reference knowledge.",
    args_schema=WikipediaSearchInput,
)
