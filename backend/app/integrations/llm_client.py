"""OpenAI-compatible LLM client (spec §6.2) — async, lazy, mock-aware.

Backs the 2-way Telegram operator agent. Points at ``settings.llm_base_url``
(Alibaba DashScope / Qwen by default) and returns ``None`` when no key is
configured, so the app always boots in demo mode.
"""
from __future__ import annotations

import logging

from ..config import settings

log = logging.getLogger("aquabro.llm")

_client = None


def get_client():
    """Return the lazily-built AsyncOpenAI client, or None when unconfigured."""
    global _client
    if not settings.llm_configured:
        return None
    if _client is None:
        # Lazy import: openai is optional at boot (mock mode has no key).
        from openai import AsyncOpenAI

        _client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url or None,
        )
    return _client


async def chat(messages, *, tools=None, tool_choice=None):
    """Run a chat completion. Returns the raw response, or None if unconfigured.

    Never raises on missing key; caller inspects ``choices[0].message``.
    """
    client = get_client()
    if client is None:
        return None
    try:
        kwargs = {"model": settings.llm_text_model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        return await client.chat.completions.create(**kwargs)
    except Exception as exc:
        log.warning("llm chat failed: %s", exc)
        return None
