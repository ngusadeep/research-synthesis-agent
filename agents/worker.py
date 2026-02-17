"""Worker node: tool-based retrieval with fallback."""

from __future__ import annotations

import logging
from typing import Any

from core.state import ResearchState, RetrievedDocument
from tools import arxiv_search, tavily_search, wikipedia_search, serpapi_search

logger = logging.getLogger(__name__)

SOURCE_TOOL_MAP = {
    "academic": (arxiv_search, serpapi_search),
    "news": (tavily_search, serpapi_search),
    "reference": (wikipedia_search, serpapi_search),
    "general": (serpapi_search, tavily_search),
}


async def worker_node(state: ResearchState) -> dict:
    """Execute retrieval per sub-query; primary + fallback tool; stream sources."""
    send_event = state.get("_send_event")
    plan = state.get("plan", [])
    all_documents: list[RetrievedDocument] = []

    for i, sub_query in enumerate(plan):
        source_type = sub_query.source_type
        query_text = sub_query.query

        if send_event:
            await send_event("steps", {
                "steps": [{
                    "id": str(i),
                    "text": f"[{source_type}] {query_text}",
                    "status": "PENDING",
                    "steps": [{"data": f"Searching {source_type} sources...", "status": "PENDING"}],
                }]
            })

        primary_tool, fallback_tool = SOURCE_TOOL_MAP.get(source_type, (serpapi_search, tavily_search))
        raw_results = await _execute_tool(primary_tool, query_text)
        if not raw_results and fallback_tool:
            logger.info("Primary tool returned no results for %r, trying fallback", query_text)
            raw_results = await _execute_tool(fallback_tool, query_text)

        documents = [
            RetrievedDocument(
                title=r.get("title", ""),
                content=r.get("content", ""),
                source=r.get("source", ""),
                source_type=r.get("source_type", source_type),
                snippet=r.get("snippet", ""),
                credibility_score=_estimate_credibility(r.get("source_type", source_type)),
                metadata=r.get("metadata", {}),
            )
            for r in raw_results
        ]
        all_documents.extend(documents)

        if send_event:
            sources = [
                {"title": doc.title, "link": doc.source, "snippet": doc.snippet, "source_type": doc.source_type, "index": idx}
                for idx, doc in enumerate(documents)
            ]
            await send_event("sources", {"sources": sources})
            await send_event("steps", {
                "steps": [{
                    "id": str(i),
                    "text": f"[{source_type}] {query_text}",
                    "status": "COMPLETED",
                    "steps": [{"data": f"Found {len(documents)} results", "status": "COMPLETED"}],
                }]
            })

        logger.info("Worker retrieved %s docs for %r (%s)", len(documents), query_text, source_type)

    return {"documents": all_documents}


async def _execute_tool(tool: Any, query: str, max_results: int = 5) -> list[dict]:
    try:
        result = await tool.ainvoke({"query": query, "max_results": max_results})
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.error("Tool %s failed for query %r: %s", tool.name, query, e)
        return []


def _estimate_credibility(source_type: str) -> float:
    return {"academic": 0.85, "reference": 0.75, "news": 0.60, "general": 0.50}.get(source_type, 0.50)
