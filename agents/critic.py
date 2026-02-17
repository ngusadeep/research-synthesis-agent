"""Critic node: quality score and refine/finalize decision."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from config import settings
from core.state import ResearchState, Critique

logger = logging.getLogger(__name__)

CRITIC_SYSTEM_PROMPT = """\
You are a rigorous research quality critic. Evaluate the given research draft and \
determine if it needs further refinement.

Evaluate on these dimensions:
1. **Gap Analysis**: Are there missing perspectives, unanswered sub-questions, or \
   important aspects of the topic not covered?
2. **Source Diversity**: Are sources varied (academic, news, reference)? Is the \
   report relying too heavily on one type?
3. **Outdated Information**: Could any claims be based on outdated information? \
   Are there areas where more recent data would improve the report?
4. **Factual Consistency**: Are there internal contradictions or unsupported claims?
5. **Completeness**: Does the report adequately address the original query?

Respond with a JSON object:
{
  "needs_refinement": true/false,
  "overall_score": 0.0-1.0,
  "gaps": ["gap1", "gap2"],
  "diversity_issues": ["issue1"],
  "outdated_concerns": ["concern1"],
  "suggestions": ["suggestion1", "suggestion2"],
  "summary": "Brief overall assessment"
}

Set needs_refinement to true ONLY if the score is below 0.7 AND there are \
actionable suggestions that would meaningfully improve the report.

Return ONLY the JSON object."""


async def critic_node(state: ResearchState) -> dict:
    """Evaluate draft; decide refine vs finalize; enforce max_iterations."""
    send_event = state.get("_send_event")
    draft = state.get("draft", "")
    query = state["query"]
    iteration = state.get("iteration", 1)
    max_iterations = state.get("max_iterations", 3)

    if send_event:
        await send_event("steps", {"steps": [{"id": "critique", "text": f"Self-critiquing (iteration {iteration})...", "status": "PENDING", "steps": []}]})

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.1,
    )

    source_types = {doc.source_type for doc in state.get("documents", [])}
    user_content = (
        f"Original query: {query}\n\n"
        f"Current iteration: {iteration} of {max_iterations}\n"
        f"Source types used: {', '.join(source_types) if source_types else 'none'}\n"
        f"Number of documents: {len(state.get('documents', []))}\n\n"
        f"Draft report:\n{draft[:4000]}"
    )

    response = await llm.ainvoke([
        SystemMessage(content=CRITIC_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ])
    content = response.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.error("Failed to parse critic response: %s", content)
        data = {"needs_refinement": False, "overall_score": 0.7, "gaps": [], "diversity_issues": [], "outdated_concerns": [], "suggestions": [], "summary": "Could not evaluate — accepting draft as-is."}

    critique = Critique(
        needs_refinement=data.get("needs_refinement", False),
        overall_score=data.get("overall_score", 0.7),
        gaps=data.get("gaps", []),
        diversity_issues=data.get("diversity_issues", []),
        outdated_concerns=data.get("outdated_concerns", []),
        suggestions=data.get("suggestions", []),
        summary=data.get("summary", ""),
    )

    if iteration >= max_iterations:
        critique.needs_refinement = False
        logger.info("Max iterations (%s) reached, finalizing", max_iterations)

    result: dict = {"critique": critique}
    if not critique.needs_refinement:
        result["final_report"] = draft
        logger.info("Critic accepted draft (score: %s)", critique.overall_score)
    else:
        logger.info("Critic requests refinement (score: %s): %s", critique.overall_score, critique.summary)

    if send_event:
        status = "COMPLETED" if not critique.needs_refinement else "PENDING"
        await send_event("steps", {
            "steps": [{
                "id": "critique",
                "text": f"Critique: {critique.summary} (score: {critique.overall_score:.1%})",
                "status": status,
                "steps": [
                    {"data": f"Gaps: {', '.join(critique.gaps) or 'None'}", "status": status},
                    {"data": f"Diversity: {', '.join(critique.diversity_issues) or 'OK'}", "status": status},
                ],
            }]
        })

    return result
