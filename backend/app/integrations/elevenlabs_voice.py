"""ElevenLabs Conversational AI integration (spec §6.2) — 3AM voice escalation.

Real bidirectional voice needs the Conversational AI agent configured + a
client-side session (mic/speaker). The backend's job here is to **arm** an
escalation: it records the system prompt + agent id so the frontend can open
the session, and it exposes the webhook the agent's ``trigger_aerator`` tool
calls (see routes: ``/api/hardware/override``).

When ElevenLabs isn't configured, ``arm_voice`` still returns the intent so
the frontend can speak the line via the browser SpeechSynthesis API —
guaranteeing the "voice takes over the speakers" demo beat works offline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import settings

log = logging.getLogger("aquabro.voice")


@dataclass(slots=True)
class VoiceIntent:
    armed: bool
    system_prompt: str
    agent_id: str
    provider: str  # "elevenlabs" | "browser_tts"
    # Public webhook the ElevenLabs agent's `trigger_aerator` tool should POST
    # to (ngrok → backend /api/hardware/override). Empty when not armed for EL.
    webhook_url: str = ""


def arm_voice(system_prompt: str) -> VoiceIntent:
    """Arm a voice escalation. Never raises."""
    if settings.voice_configured:
        webhook = f"{settings.public_base_url.rstrip('/')}/api/hardware/override"
        # Agent id may carry a "?branchId=..." (dashboard editing pin); the
        # browser SDK wants the bare id for the public startSession path.
        agent_id = settings.elevenlabs_agent_id.split("?")[0]
        log.info(
            "[ELEVENLABS] voice escalation armed (agent %s, webhook %s).",
            agent_id, webhook,
        )
        return VoiceIntent(
            armed=True,
            system_prompt=system_prompt,
            agent_id=agent_id,
            provider="elevenlabs",
            webhook_url=webhook,
        )
    log.info("[BROWSER TTS] voice escalation armed (no ElevenLabs key).")
    return VoiceIntent(
        armed=True,
        system_prompt=system_prompt,
        agent_id="",
        provider="browser_tts",
    )
