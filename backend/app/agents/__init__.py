"""Reasoning agents.

All agents here are **pure**: they take data in, return structured results +
reasoning notes, and perform no I/O. HTTP/webhook/voice dispatch lives in
``integrations`` and is driven by the engine. This keeps the reasoning core
deterministic and unit-testable (see backend/tests/test_telemetry_verify.py).

Agents (spec §2):
  telemetry.verify  — Telemetry Verification Agent (covariant sensor-fault detect)
  context.*         — Context Agent (ambient + organic load → TAN estimate)
  causal.diagnose   — Causal Diagnostics Agent (math models → risks + toxicity)
  action.plan       — Action Planner Agent (risks → deterministic payloads/intent)
"""
from . import action, causal, context, telemetry

__all__ = ["action", "causal", "context", "telemetry"]
