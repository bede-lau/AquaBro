"""AquaBro backend — fault-tolerant multi-agent RAS monitoring.

A single FastAPI process runs the full reasoning loop:

    telemetry ─┐
    vision ────┤
    context ───┼─▶ Causal Diagnostics ──(FSM)──▶ Action Planner ──▶ hardware/voice/telegram
                         │
                  in-memory causal graph + biochemical math models
"""
__version__ = "0.1.0"
