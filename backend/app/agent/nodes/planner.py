"""Planner node: analyzes the query and generates sub-queries with source hints."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.agent.state import ResearchState, SubQuery

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """\
You are a research planning agent. Given a user query, you must generate a set of \
focused sub-queries that, when answered together, will provide a comprehensive \
understanding of the topic.

For each sub-query, assign a source_type:
- "academic" → for scientific, peer-reviewed, or technical topics (uses ArXiv)
- "news" → for current events, recent developments, trends (uses Tavily web search)
- "reference" → for definitions, historical context, established knowledge (uses Wikipedia)
- "general" → for corporate info, social media, or anything else (uses SerpAPI/Google)

Rules:
1. Generate 3-5 sub-queries. Each should cover a different angle of the topic.
2. Ensure source diversity — use at least 2 different source types.
3. If this is a RE-PLAN after a critique, incorporate the critique feedback to fill gaps.
4. Keep sub-queries focused and specific.

Respond with a JSON array of objects:
[
  {"query": "...", "source_type": "academic|news|reference|general", "rationale": "..."},
  ...
]

Return ONLY the JSON array, no other text."""

REPLAN_TEMPLATE = """\
Original query: {query}

Previous critique identified these issues:
- Gaps: {gaps}
- Diversity issues: {diversity_issues}
- Suggestions: {suggestions}

Current iteration: {iteration} of {max_iterations}

Generate new sub-queries that address these gaps. Focus on areas not yet covered."""


async def planner_node(state: ResearchState) -> dict:
    """
    Plan the research by generating sub-queries.

    On first run, analyzes the query directly.
    On re-plan (after critique), incorporates feedback to address gaps.
    """
    send_event = state.get("_send_event")
    query = state["query"]
    iteration = state.get("iteration", 0)
    critique = state.get("critique")

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.3,
    )

    # Build the user message
    if critique and iteration > 0:
        user_content = REPLAN_TEMPLATE.format(
            query=query,
            gaps="; ".join(critique.gaps) if critique.gaps else "None",
            diversity_issues="; ".join(critique.diversity_issues) if critique.diversity_issues else "None",
            suggestions="; ".join(critique.suggestions) if critique.suggestions else "None",
            iteration=iteration,
            max_iterations=state.get("max_iterations", 3),
        )
    else:
        user_content = f"Research query: {query}"

    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    response = await llm.ainvoke(messages)
    content = response.content.strip()

    # Parse the JSON response
    # Strip markdown code fences if present
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        raw_plans = json.loads(content)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse planner response: {content}")
        raw_plans = [{"query": query, "source_type": "general", "rationale": "Fallback to original query"}]

    sub_queries = [
        SubQuery(
            query=p.get("query", query),
            source_type=p.get("source_type", "general"),
            rationale=p.get("rationale", ""),
        )
        for p in raw_plans
    ]

    logger.info(f"Planner generated {len(sub_queries)} sub-queries (iteration {iteration})")

    # Stream plan step to frontend
    if send_event:
        steps = [
            {
                "id": str(i),
                "text": f"[{sq.source_type}] {sq.query}",
                "status": "PENDING",
                "steps": [],
            }
            for i, sq in enumerate(sub_queries)
        ]
        await send_event("steps", {"steps": steps})

    return {
        "plan": sub_queries,
        "iteration": iteration + 1,
    }
