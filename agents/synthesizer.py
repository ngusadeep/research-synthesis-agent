"""Synthesizer node: report and conflict extraction."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from config import settings
from core.state import ResearchState, Conflict, SourceMeta

logger = logging.getLogger(__name__)

SYNTHESIZER_SYSTEM_PROMPT = """\
You are a research synthesis expert. Given a set of retrieved documents from multiple \
sources, synthesize them into a comprehensive, well-structured research report.

Your report MUST:
1. Be written in Markdown format with clear headings and sections.
2. Include an Executive Summary at the top.
3. Organize findings into logical thematic sections.
4. Cite sources inline using numbered references like [1], [2], etc.
5. Include a "Sources" section at the end listing all references.
6. Detect and explicitly note any CONFLICTS between sources in a dedicated "Conflicts & Contradictions" section.
7. Assess source credibility where relevant.

For conflict detection, look for:
- Contradictory claims, statistics, or dates
- Differing expert opinions
- Methodological disagreements

Also produce a JSON block at the very end (after ---) with detected conflicts:
```json
{"conflicts": [{"claim_a": "...", "source_a": "...", "claim_b": "...", "source_b": "...", "description": "..."}]}
```

Write a thorough, balanced report. Do not fabricate information."""

DOCUMENT_TEMPLATE = """\
Source [{index}]: {title}
Type: {source_type} | Credibility: {credibility}
URL: {source}
---
{content}
---"""


async def synthesizer_node(state: ResearchState) -> dict:
    """Synthesize documents into report; stream tokens; extract conflicts."""
    send_event = state.get("_send_event")
    query = state["query"]
    documents = state.get("documents", [])

    if not documents:
        draft = "# Research Report\n\nNo documents were retrieved. Please try a different query."
        if send_event:
            await send_event("answer", {"answer": {"text": draft}})
        return {"draft": draft, "conflicts": [], "sources_metadata": []}

    doc_texts = []
    sources_metadata = []
    for i, doc in enumerate(documents):
        doc_texts.append(DOCUMENT_TEMPLATE.format(
            index=i + 1,
            title=doc.title,
            source_type=doc.source_type,
            credibility=f"{doc.credibility_score:.0%}",
            source=doc.source,
            content=doc.content[:1500],
        ))
        sources_metadata.append(SourceMeta(
            url=doc.source,
            title=doc.title,
            source_type=doc.source_type,
            credibility_score=doc.credibility_score,
        ))

    user_content = f"Research query: {query}\n\nRetrieved documents ({len(documents)} total):\n\n" + "\n\n".join(doc_texts)

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.2,
        streaming=True,
    )
    messages = [
        SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    if send_event:
        await send_event("steps", {"steps": [{"id": "synthesis", "text": "Synthesizing report...", "status": "PENDING", "steps": []}]})

    full_draft = ""
    async for chunk in llm.astream(messages):
        token = chunk.content
        if token:
            full_draft += token
            if send_event:
                await send_event("answer", {"answer": {"text": token}})

    if send_event:
        await send_event("steps", {"steps": [{"id": "synthesis", "text": "Synthesizing report...", "status": "COMPLETED", "steps": []}]})

    conflicts = _extract_conflicts(full_draft)
    logger.info("Synthesizer produced %s chars, %s conflicts", len(full_draft), len(conflicts))

    return {"draft": full_draft, "conflicts": conflicts, "sources_metadata": sources_metadata}


def _extract_conflicts(draft: str) -> list[Conflict]:
    conflicts = []
    try:
        if "```json" in draft:
            json_block = draft.split("```json")[-1].split("```")[0].strip()
            data = json.loads(json_block)
            for c in data.get("conflicts", []):
                conflicts.append(Conflict(
                    claim_a=c.get("claim_a", ""),
                    source_a=c.get("source_a", ""),
                    claim_b=c.get("claim_b", ""),
                    source_b=c.get("source_b", ""),
                    description=c.get("description", ""),
                ))
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Could not extract conflicts JSON: %s", e)
    return conflicts
