"""Telegram Bot client (spec §6.1) — async diagnostic alerts."""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("aquabro.telegram")


class TelegramClient:
    async def send(self, text: str) -> bool:
        if not settings.telegram_configured:
            log.info("[MOCK TELEGRAM] %s", text)
            return False
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(
                    url, json={"chat_id": settings.telegram_chat_id, "text": text}
                )
                return r.status_code == 200
        except Exception as exc:
            log.warning("telegram send failed: %s", exc)
            return False
