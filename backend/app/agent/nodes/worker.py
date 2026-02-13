"""Worker node: executes retrieval for a single sub-query using the appropriate tool."""

from __future__ import annotations

import logging
from typing import Any

from app.agent.state import ResearchState, RetrievedDocument
from app.agent.tools import arxiv_search, tavily_search, wikipedia_search, serpapi_search

logger = logging.getLogger(__name__)

# Map source types to their primary and fallback tools
SOURCE_TOOL_MAP = {
    "academic": (arxiv_search, serpapi_search),
    "news": (tavily_search, serpapi_search),
    "reference": (wikipedia_search, serpapi_search),
    "general": (serpapi_search, tavily_search),
}


async def worker_node(state: ResearchState) -> dict:
    """
    Execute retrieval for a single sub-query.

    This node is invoked via Send() — one instance per sub-query.
    It selects the appropriate tool based on source_type, executes
    the search, and falls back to an alternative tool if the primary
    returns no results.
    """
    send_event = state.get("_send_event")
    plan = state.get("plan", [])

    all_documents: list[RetrievedDocument] = []

    for i, sub_query in enumerate(plan):
        source_type = sub_query.source_type
        query_text = sub_query.query

        # Notify frontend of worker start
        if send_event:
            await send_event("steps", {
                "steps": [{
                    "id": str(i),
                    "text": f"[{source_type}] {query_text}",
                    "status": "PENDING",
                    "steps": [{"data": f"Searching {source_type} sources...", "status": "PENDING"}],
                }]
            })

        primary_tool, fallback_tool = SOURCE_TOOL_MAP.get(
            source_type, (serpapi_search, tavily_search)
        )

        # Try primary tool
        raw_results = await _execute_tool(primary_tool, query_text)

        # Fallback if primary returned nothing
        if not raw_results and fallback_tool:
            logger.info(f"Primary tool returned no results for '{query_text}', trying fallback")
            raw_results = await _execute_tool(fallback_tool, query_text)

        # Convert raw results to RetrievedDocument objects
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

        # Stream sources to frontend
        if send_event:
            sources = [
                {
                    "title": doc.title,
                    "link": doc.source,
                    "snippet": doc.snippet,
                    "source_type": doc.source_type,
                    "index": idx,
                }
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

        logger.info(f"Worker retrieved {len(documents)} docs for '{query_text}' ({source_type})")

    return {"documents": all_documents}


async def _execute_tool(tool: Any, query: str, max_results: int = 5) -> list[dict]:
    """Execute a search tool with error handling."""
    try:
        result = await tool.ainvoke({"query": query, "max_results": max_results})
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        logger.error(f"Tool {tool.name} failed for query '{query}': {e}")
        return []


def _estimate_credibility(source_type: str) -> float:
    """Estimate initial credibility based on source type."""
    credibility_map = {
        "academic": 0.85,
        "reference": 0.75,
        "news": 0.60,
        "general": 0.50,
    }
    return credibility_map.get(source_type, 0.50)
