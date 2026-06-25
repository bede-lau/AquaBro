"""Action Planner Agent (spec §2.5).

Translates diagnostic intents into deterministic API payloads + alert/voice
intent. It only *plans* — the engine performs the actual HTTP/webhook/voice
dispatch (keeps this pure and testable).

Implements the concrete control laws from spec §3:
  §3.2 hypoxia  → emergency aerator override (bypasses standard alerts)
  §3.3 toxicity → feed rate × 0.5 and lock the valve
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..causal.math_models import reduced_feed_rate
from ..schemas import HardwareState
from .causal import CausalResult

VOICE_SYSTEM_PROMPT = (
    "You are the AquaBro Emergency Bio-Security Officer. A critical hypoxia "
    "event has been detected in Tank 1. Inform the operator concisely and ask "
    "whether to EXECUTE emergency aeration or CANCEL. Await their voice command."
)


@dataclass(slots=True)
class ActionPlan:
    aerator: str  # "ACTIVE" | "STANDBY" | None (None = no change)
    feed_valve: str  # "LOCKED" | "ACTIVE" | None
    feed_rate_pct: float | None
    telegram_text: str | None
    voice_prompt: str | None  # system prompt for ElevenLabs, or None
    webhooks: list[dict]  # deterministic payloads for /api/hardware/override
    notes: list[str] = field(default_factory=list)


def _risk(result: CausalResult, name: str):
    return next((r for r in result.risks if r.name == name), None)


def plan(result: CausalResult, hardware: HardwareState) -> ActionPlan:
    """Produce a deterministic action plan from the causal diagnosis."""
    notes: list[str] = []
    aerator: str | None = None
    feed_valve: str | None = None
    feed_rate_pct: float | None = None
    telegram_text: str | None = None
    voice_prompt: str | None = None
    webhooks: list[dict] = []

    hypo = _risk(result, "Hypoxia")
    tox = _risk(result, "Ammonia_Toxicity")

    # §3.2 — emergency aeration on confirmed critical hypoxia.
    if hypo and hypo.active and hypo.severity == "CRITICAL":
        aerator = "ACTIVE"
        webhooks.append({"device": "aerator", "action": "ACTIVE", "reason": "hypoxia_override"})
        voice_prompt = VOICE_SYSTEM_PROMPT
        notes.append("[ACTION] §3.2 emergency aerator override dispatched; voice escalation armed.")

    # §3.3 — pre-emptive feed lock when toxicity is climbing/toxic.
    if tox and tox.active and (tox.severity == "CRITICAL" or result.toxicity.slope_per_min > 0):
        feed_valve = "LOCKED"
        feed_rate_pct = reduced_feed_rate(hardware.feed_rate_pct)
        webhooks.append(
            {"device": "feed_valve", "action": "LOCKED", "rate_pct": feed_rate_pct,
             "reason": "toxicity_slope_positive"}
        )
        notes.append(
            f"[ACTION] §3.3 feed valve locked, rate {hardware.feed_rate_pct:.0f}%→"
            f"{feed_rate_pct:.0f}%."
        )
    elif hardware.feed_valve == "LOCKED" and not (tox and tox.active):
        # restore feeding once toxicity clears
        feed_valve = "ACTIVE"
        feed_rate_pct = 100.0
        webhooks.append({"device": "feed_valve", "action": "ACTIVE", "rate_pct": 100.0,
                         "reason": "toxicity_cleared"})
        notes.append("[ACTION] toxicity cleared — feed valve restored.")

    # Telegram alert on any CRITICAL risk (async diagnostic channel).
    criticals = [r for r in result.risks if r.active and r.severity == "CRITICAL"]
    if criticals:
        body = "URGENT: " + " | ".join(f"{r.name}: {r.evidence}" for r in criticals)
        telegram_text = body
        notes.append("[ACTION] Telegram diagnostic alert queued.")

    return ActionPlan(
        aerator=aerator,
        feed_valve=feed_valve,
        feed_rate_pct=feed_rate_pct,
        telegram_text=telegram_text,
        voice_prompt=voice_prompt,
        webhooks=webhooks,
        notes=notes,
    )
