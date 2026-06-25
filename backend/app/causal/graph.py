"""In-memory biochemical causal knowledge graph (spec §5.2).

Deliberately *not* Neo4j: the domain structure is small and static, so an
in-process graph gives identical reasoning, no DB round-trip per tick, and
one fewer live-demo failure surface. The UI renders this exact structure as
an interactive panel (the "knowledge graph" narrative is preserved).

Graph topology (read-only facts) lives here as data; node *state* is coloured
at runtime from the live ``TankState``.
"""
from __future__ import annotations

from ..schemas import (
    AmbientContext,
    CausalGraph,
    GraphEdge,
    GraphNode,
    HardwareState,
    RiskAssessment,
    TankState,
    Telemetry,
    ToxicityAssessment,
    VisionAssessment,
)

# ── Static topology ──────────────────────────────────────────────────
NODES: list[tuple[str, str, str]] = [
    # (id, label, kind)
    ("DO_Probe", "DO Probe", "Sensor"),
    ("pH_Probe", "pH Probe", "Sensor"),
    ("Temp_Probe", "Temp Probe", "Sensor"),
    ("Dissolved_Oxygen", "Dissolved O₂", "Parameter"),
    ("pH", "pH", "Parameter"),
    ("Temperature", "Temperature", "Parameter"),
    ("Ammonia", "Ammonia (NH₃)", "Parameter"),
    ("Hypoxia", "Hypoxia", "Risk"),
    ("Ammonia_Toxicity", "Ammonia Toxicity", "Risk"),
    ("Aerator_Pump", "Aerator Pump", "Hardware"),
    ("Feed_Valve", "Feed Valve", "Hardware"),
]

EDGES: list[tuple[str, str, str]] = [
    # (src, dst, rel)
    ("DO_Probe", "Dissolved_Oxygen", "MEASURES"),
    ("pH_Probe", "pH", "MEASURES"),
    ("Temp_Probe", "Temperature", "MEASURES"),
    ("Dissolved_Oxygen", "Hypoxia", "INFLUENCES"),
    ("Temperature", "Hypoxia", "INFLUENCES"),       # warm water holds less O₂
    ("pH", "Ammonia_Toxicity", "INFLUENCES"),       # pH shifts the toxic fraction
    ("Ammonia", "Ammonia_Toxicity", "INFLUENCES"),
    ("Temperature", "Ammonia_Toxicity", "INFLUENCES"),  # pKa is temp-dependent
    ("Aerator_Pump", "Hypoxia", "MITIGATES"),
    ("Feed_Valve", "Ammonia_Toxicity", "MITIGATES"),
]

# node_id -> list of hardware ids that MITIGATE the risk it represents
_MITIGATIONS: dict[str, list[str]] = {
    "Hypoxia": ["Aerator_Pump"],
    "Ammonia_Toxicity": ["Feed_Valve"],
}


def nodes() -> list[tuple[str, str, str]]:
    return list(NODES)


def edges() -> list[tuple[str, str, str]]:
    return list(EDGES)


def mitigations_for(risk_id: str) -> list[str]:
    """Hardware nodes that mitigate a given risk node."""
    return list(_MITIGATIONS.get(risk_id, []))


# ── Runtime colouring ────────────────────────────────────────────────
def _do_state(do: float, fault: bool) -> str:
    if fault:
        return "critical"
    if do <= 1.5:
        return "critical"
    if do < 3.0:
        return "elevated"
    return "nominal"


def _ph_state(ph: float) -> str:
    if ph >= 8.4:
        return "critical"
    if ph > 8.0:
        return "elevated"
    return "nominal"


def _temp_state(temp_c: float) -> str:
    if temp_c >= 31:
        return "critical"
    if temp_c > 29:
        return "elevated"
    return "nominal"


def _risk_state(risks: list[RiskAssessment], name: str) -> str:
    for r in risks:
        if r.name == name and r.active:
            return "critical" if r.severity == "CRITICAL" else "elevated"
    return "nominal"


def build_graph_view(state: TankState) -> CausalGraph:
    """Project live tank state onto the static graph for the UI panel."""
    tel = state.telemetry
    toxic = state.toxicity
    fault = state.sensor_fault

    def colour(node_id: str) -> str:
        if node_id == "DO_Probe":
            return _do_state(tel.do_level, fault)
        if node_id == "pH_Probe":
            return "critical" if fault else _ph_state(tel.ph_level)
        if node_id == "Temp_Probe":
            return "critical" if fault else _temp_state(tel.temp_c)
        if node_id == "Dissolved_Oxygen":
            return _do_state(tel.do_level, fault)
        if node_id == "pH":
            return _ph_state(tel.ph_level)
        if node_id == "Temperature":
            return _temp_state(tel.temp_c)
        if node_id == "Ammonia":
            if toxic and toxic.toxic:
                return "critical"
            if toxic and toxic.nh3_mg_l > 0.8 * toxic.threshold_mg_l:
                return "elevated"
            return "nominal"
        if node_id in ("Hypoxia", "Ammonia_Toxicity"):
            return _risk_state(state.risks, node_id)
        if node_id == "Aerator_Pump":
            return "active" if state.hardware.aerator == "ACTIVE" else "nominal"
        if node_id == "Feed_Valve":
            return "locked" if state.hardware.feed_valve == "LOCKED" else "nominal"
        return "nominal"

    g_nodes = [
        GraphNode(id=nid, label=label, kind=kind, state=colour(nid))
        for nid, label, kind in NODES
    ]
    g_edges = [GraphEdge(src=s, dst=d, rel=r) for s, d, r in EDGES]
    return CausalGraph(nodes=g_nodes, edges=g_edges)


# Re-export schema types used by callers for convenience.
__all__ = [
    "nodes",
    "edges",
    "mitigations_for",
    "build_graph_view",
    "CausalGraph",
    "GraphNode",
    "GraphEdge",
    "Telemetry",
    "VisionAssessment",
    "AmbientContext",
    "ToxicityAssessment",
    "RiskAssessment",
    "HardwareState",
]
