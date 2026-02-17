"""Intent classification: distinguish research questions from casual chat."""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You classify user messages into exactly one category.

- "research": The user is asking for factual, multi-source research. Examples: "What do you know about X?", "Compare A and B", "Latest developments in X", "Why does X happen?", topic questions that benefit from searching multiple sources.
- "chat": Greetings, small talk, thanks, goodbye, simple clarifications, or questions that do not need external research. Examples: "Hello", "How are you?", "Thanks", "What can you do?", "Tell me a joke".

Reply with exactly one word: research or chat. No other text."""


async def classify_research_vs_chat(user_message: str) -> str:
    """Return 'research' or 'chat' based on user intent. Uses a fast LLM call."""
    if not user_message or not user_message.strip():
        return "chat"
    text = user_message.strip().lower()
    # Obvious short greetings / small talk -> chat without calling LLM
    if len(text) < 80 and re.match(
        r"^(hi|hey|hello|howdy|yo|sup|thanks|thank you|bye|goodbye|good morning|good night|how are you|what('s|s) up|what can you do|tell me a joke)\b",
        text,
    ):
        return "chat"
    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )
        response = await llm.ainvoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_message),
            ]
        )
        content = (response.content or "").strip().lower()
        if "research" in content:
            return "research"
        return "chat"
    except Exception as e:
        logger.warning("Intent classification failed, defaulting to research: %s", e)
        return "research"
