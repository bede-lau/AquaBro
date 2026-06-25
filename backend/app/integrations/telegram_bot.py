"""2-way Telegram operator agent (spec §6.2).

Long-polls Telegram getUpdates for inbound commands from the authorized
operator, routes them through an LLM tool-calling loop (when configured) or a
deterministic keyword fallback, and mutates engine.hardware to control the
aerator/feed_valve. Replies via the existing one-way TelegramClient.

Safety: the ONLY access boundary is ``settings.telegram_chat_id``. Messages
from any other chat are ignored; commands from the operator fire immediately.
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx

from ..config import settings
from .llm_client import chat as llm_chat
from .telegram import TelegramClient

if False:  # TYPE_CHECKING-style guard without import cycle
    from ..engine import Engine

log = logging.getLogger("aquabro.telegram_agent")

_SYSTEM_PROMPT = (
    "You are AquaBro, an assistant for a tilapia RAS site operator. "
    "Answer briefly in plain English. You can read tank conditions and "
    "control the aerator pump and feed valve."
)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_tank_status",
            "description": "Read current tank water-quality and hardware status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_actuator",
            "description": "Control the aerator pump or feed valve.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "enum": ["aerator", "feed_valve"]},
                    "action": {"type": "string", "enum": ["on", "off", "lock"]},
                    "feed_rate_pct": {
                        "type": "integer",
                        "nullable": True,
                        "description": "Optional new feed rate percentage (feed_valve only).",
                    },
                },
                "required": ["device", "action"],
            },
        },
    },
]

_LONGPOLL_TIMEOUT = 30


class TelegramAgent:
    def __init__(self, engine: "Engine", telegram_client: TelegramClient) -> None:
        self.engine = engine
        self.telegram = telegram_client
        self._offset = 0
        self._disabled_logged = False

    # ── main loop ────────────────────────────────────────────────────
    async def run(self, stop_event: asyncio.Event) -> None:
        if not settings.telegram_agent_ready:
            log.info("telegram agent disabled (mock/off)")
            return
        token = settings.telegram_bot_token
        chat_id = int(settings.telegram_chat_id)
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        log.info("telegram agent polling chat_id=%s", chat_id)
        try:
            async with httpx.AsyncClient(timeout=_LONGPOLL_TIMEOUT + 10) as client:
                while not stop_event.is_set():
                    try:
                        r = await client.post(
                            url,
                            json={"offset": self._offset, "timeout": _LONGPOLL_TIMEOUT},
                        )
                        if r.status_code != 200:
                            log.warning("getUpdates http %d", r.status_code)
                            await asyncio.sleep(5)
                            continue
                        for upd in r.json().get("result", []):
                            self._offset = upd.get("update_id", self._offset) + 1
                            msg = upd.get("message") or upd.get("edited_message")
                            if not msg:
                                continue
                            if msg.get("chat", {}).get("id") != chat_id:
                                continue  # unauthorized chat — ignore
                            text = (msg.get("text") or "").strip()
                            if not text:
                                continue
                            await self._handle(text)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        log.exception("telegram agent update failed")
        except asyncio.CancelledError:
            pass

    # ── dispatch ─────────────────────────────────────────────────────
    async def _handle(self, text: str) -> None:
        try:
            if settings.llm_configured:
                reply = await self._handle_llm(text)
            else:
                reply = await self._handle_fallback(text)
            if reply:
                await self.telegram.send(reply)
        except Exception:
            log.exception("telegram agent handle failed")

    # ── status builder ───────────────────────────────────────────────
    def _status_string(self) -> str:
        s = self.engine.snapshot()
        t = s.telemetry
        tox = s.toxicity
        vis = s.vision
        nh3 = tox.nh3_mg_l if tox else 0.0
        nh3_state = "toxic" if (tox and tox.toxic) else "safe"
        fish_count = vis.fish_count if vis else 0
        activity = vis.activity_index if vis else 0.0
        return (
            f"DO {t.do_level:.2f} mg/L, pH {t.ph_level:.2f}, "
            f"temp {t.temp_c:.1f} C, NH3 {nh3:.4f} mg/L ({nh3_state}), "
            f"fish {fish_count} (activity {activity:.2f}), "
            f"aerator {s.hardware.aerator}, "
            f"feed_valve {s.hardware.feed_valve} @ {s.hardware.feed_rate_pct:.0f}%, "
            f"state {s.fsm_state}."
        )

    # ── actuator mutation (mirror main.py override logic) ────────────
    async def _control_actuator(
        self, device: str, action: str, feed_rate_pct: int | None = None
    ) -> str:
        hw = self.engine.hardware
        if device == "aerator":
            new = "ACTIVE" if action == "on" else "STANDBY"
            if new != hw.aerator:
                hw = hw.model_copy(update={"aerator": new})
                self.engine.hardware = hw
                await self.engine.emit_narrative(
                    "info",
                    "Operator (Telegram) started the aerator."
                    if new == "ACTIVE"
                    else "Operator (Telegram) stopped the aerator.",
                )
                await self.engine.publish_hardware()
            return f"aerator is now {new}."
        if device == "feed_valve":
            new = "LOCKED" if action == "lock" else "ACTIVE"
            update: dict = {"feed_valve": new}
            if feed_rate_pct is not None:
                update["feed_rate_pct"] = float(feed_rate_pct)
            if new != hw.feed_valve or feed_rate_pct is not None:
                hw = hw.model_copy(update=update)
                self.engine.hardware = hw
                await self.engine.emit_narrative(
                    "info",
                    "Operator (Telegram) paused the auto-feeder."
                    if new == "LOCKED"
                    else "Operator (Telegram) resumed the auto-feeder.",
                )
                await self.engine.publish_hardware()
            return f"feed_valve is now {new}."
        return f"unknown device {device}."

    # ── LLM tool-calling loop ────────────────────────────────────────
    async def _handle_llm(self, text: str) -> str:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        for _ in range(4):
            resp = await llm_chat(messages, tools=_TOOLS)
            if resp is None:
                # LLM unavailable mid-loop — fall back.
                return await self._handle_fallback(text)
            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                return (msg.content or "").strip() or self._status_string()
            # append assistant tool_call message, then results
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await self._dispatch_tool(name, args)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result}
                )
        return self._status_string()

    async def _dispatch_tool(self, name: str, args: dict) -> str:
        if name == "get_tank_status":
            return self._status_string()
        if name == "control_actuator":
            device = args.get("device", "")
            action = args.get("action", "")
            rate = args.get("feed_rate_pct")
            return await self._control_actuator(device, action, rate)
        return f"unknown tool {name}."

    # ── deterministic fallback (LLM not configured) ──────────────────
    async def _handle_fallback(self, text: str) -> str:
        low = text.lower()
        if "ammonia" in low or "nh3" in low:
            tox = self.engine.snapshot().toxicity
            nh3 = tox.nh3_mg_l if tox else 0.0
            state = "toxic" if (tox and tox.toxic) else "safe"
            return f"Ammonia (NH3) is {nh3:.4f} mg/L — {state}."
        if any(k in low for k in ("status", "how", "how's")):
            return self._status_string()
        if any(k in low for k in ("aerator", "pump", "oxygen")):
            if any(k in low for k in ("off", "stop")):
                await self._control_actuator("aerator", "off")
                return "Aerator stopped."
            await self._control_actuator("aerator", "on")
            return "Aerator started to push oxygen into the tank."
        if "feed" in low:
            if any(k in low for k in ("lock", "stop", "pause")):
                await self._control_actuator("feed_valve", "lock")
                return "Auto-feeder paused."
            if any(k in low for k in ("on", "start", "resume")):
                await self._control_actuator("feed_valve", "on")
                return "Auto-feeder resumed."
        return self._status_string()
