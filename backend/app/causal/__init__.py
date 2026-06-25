"""Causal engine: biochemical math + in-memory knowledge graph + FSM.

This package is the deterministic reasoning core — no LLM, no external
calls. It is pure and fully unit-tested (see backend/tests). Everything
downstream (agents, engine) composes these primitives.
"""
from .fsm import FSMState, Signals, Transition, transition
from .graph import build_graph_view, edges, nodes, mitigations_for
from .math_models import (
    HYPoxIA_DO_CRITICAL,
    HYPoxIA_T_CRITICAL_S,
    NH3_THRESHOLD,
    assess_toxicity,
    pka_ammonia,
    reduced_feed_rate,
    unionized_nh3_fraction,
)

__all__ = [
    "FSMState",
    "Signals",
    "Transition",
    "transition",
    "build_graph_view",
    "nodes",
    "edges",
    "mitigations_for",
    "assess_toxicity",
    "pka_ammonia",
    "unionized_nh3_fraction",
    "reduced_feed_rate",
    "NH3_THRESHOLD",
    "HYPoxIA_DO_CRITICAL",
    "HYPoxIA_T_CRITICAL_S",
]
