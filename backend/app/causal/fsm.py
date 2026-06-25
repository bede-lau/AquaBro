"""Deterministic finite-state machine for the system lifecycle.

States (spec §7 demo flow, generalized):

    NORMAL ──WARN──▶ AT_RISK ──CRITICAL──▶ CRITICAL ──action──▶ MITIGATING
      ▲                 │                      │                     │
      └─── INFO ────────┘                      │     recovering       │
                                              ▼                     ▼
                                           CRITICAL ◀──cancel── MITIGATING
                                                                  RECOVERING ──INFO──▶ NORMAL

Pure function: ``transition(current, signals)`` — no side effects, fully
unit-tested. The engine drives it each tick; actions are dispatched on the
transition into CRITICAL.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FSMState(str, Enum):
    NORMAL = "NORMAL"
    AT_RISK = "AT_RISK"
    CRITICAL = "CRITICAL"
    MITIGATING = "MITIGATING"
    RECOVERING = "RECOVERING"


@dataclass(slots=True)
class Signals:
    """Aggregated inputs the FSM reacts to.

    severity: max severity across active risks (INFO | WARN | CRITICAL).
    action_active: a mitigation hardware action is currently engaged
        (aerator running, or feed valve locked by the AI).
    recovering: metrics are trending back to safe AND severity <= WARN.
    """

    severity: str = "INFO"
    action_active: bool = False
    recovering: bool = False


@dataclass(slots=True)
class Transition:
    state: FSMState
    changed: bool
    reason: str


def _sev_rank(s: str) -> int:
    return {"INFO": 0, "WARN": 1, "CRITICAL": 2}.get(s, 0)


def transition(current: FSMState, sig: Signals) -> Transition:
    s = current

    if s is FSMState.NORMAL:
        if sig.severity == "CRITICAL":
            return Transition(FSMState.CRITICAL, True, "critical risk emerged")
        if sig.severity == "WARN":
            return Transition(FSMState.AT_RISK, True, "elevated risk detected")
        return Transition(FSMState.NORMAL, False, "stable")

    if s is FSMState.AT_RISK:
        if sig.severity == "CRITICAL":
            return Transition(FSMState.CRITICAL, True, "risk escalated to critical")
        if sig.severity == "INFO":
            return Transition(FSMState.NORMAL, True, "risk cleared")
        return Transition(FSMState.AT_RISK, False, "holding at risk")

    if s is FSMState.CRITICAL:
        if sig.action_active:
            return Transition(FSMState.MITIGATING, True, "mitigation engaged")
        return Transition(FSMState.CRITICAL, False, "awaiting mitigation")

    if s is FSMState.MITIGATING:
        if sig.severity == "INFO":
            return Transition(FSMState.NORMAL, True, "incident resolved")
        if sig.severity == "CRITICAL" and sig.recovering:
            return Transition(FSMState.RECOVERING, True, "metrics recovering")
        if sig.severity == "CRITICAL" and not sig.action_active:
            return Transition(FSMState.CRITICAL, True, "mitigation disengaged")
        return Transition(FSMState.MITIGATING, False, "mitigating")

    if s is FSMState.RECOVERING:
        if sig.severity == "CRITICAL":
            return Transition(FSMState.CRITICAL, True, "relapsed to critical")
        if sig.severity == "INFO":
            return Transition(FSMState.NORMAL, True, "fully recovered")
        return Transition(FSMState.RECOVERING, False, "still recovering")

    # Defensive default — unknown state.
    return Transition(FSMState.NORMAL, False, "reset")
