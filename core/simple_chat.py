"""Simple chat: stream a single LLM reply (no research pipeline). Used for Quick mode and when intent=chat in Research mode."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any, Awaitable, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import settings

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM = "You are a helpful assistant. Answer concisely and clearly. For greetings and small talk, keep it brief and friendly."


async def stream_simple_chat(
    user_message: str,
    system_prompt: str = DEFAULT_SYSTEM,
) -> AsyncGenerator[str, None]:
    """Stream LLM reply tokens for a single user message. Yields text chunks."""
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.7,
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    async for chunk in llm.astream(messages):
        if chunk.content:
            yield chunk.content


async def run_simple_chat_and_send(
    user_message: str,
    send_event: Callable[[str, dict], Awaitable[Any]],
    system_prompt: str = DEFAULT_SYSTEM,
) -> None:
    """Stream simple chat and emit SSE-style events (answer chunks, then done)."""
    full_text = ""
    async for chunk in stream_simple_chat(user_message, system_prompt=system_prompt):
        full_text += chunk
        await send_event("answer", {"answer": {"text": chunk}})
    await send_event("done", {"type": "done", "status": "complete"})
