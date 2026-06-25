"""Pydantic schemas — the public API contract the frontend consumes.

Kept dependency-free of ORM so the wire format is explicit and stable.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Telemetry ────────────────────────────────────────────────────────
class Telemetry(BaseModel):
    timestamp: datetime
    tank_id: str = "TANK-01"
    do_level: float
    ph_level: float
    temp_c: float
    is_override: bool = False


class VisionAssessment(BaseModel):
    """Output of the Vision Agent — biological ground truth."""

    activity_index: float = Field(
        ..., description="0..1 normalized motion energy (1 = frantic, 0 = still)"
    )
    lethargy: bool
    surface_piping: bool
    fish_count: int = 0
    mean_depth_norm: float = Field(
        ..., description="0..1, 0=surface, 1=bottom — flags surface piping"
    )
    fault: bool = False  # detector unavailable / mocked


class AmbientContext(BaseModel):
    """Output of the Context Agent."""

    air_temp_c: float | None = None
    humidity_pct: float | None = None
    description: str = "synthetic baseline"
    recent_feed_mass_g: float = 0.0
    source: Literal["openweather", "mock"] = "mock"


class ToxicityAssessment(BaseModel):
    """Causal Agent's ammonia math (§3.1)."""

    tan: float = Field(..., description="Total Ammonia Nitrogen mg/L")
    ph: float
    temp_c: float
    pka: float
    nh3_fraction: float
    nh3_mg_l: float
    threshold_mg_l: float = 0.05
    toxic: bool
    slope_per_min: float = 0.0  # toxicity trajectory


class RiskAssessment(BaseModel):
    name: str
    severity: Literal["INFO", "WARN", "CRITICAL"]
    active: bool
    evidence: str
    mitigations: list[str] = Field(default_factory=list)


class HardwareState(BaseModel):
    aerator: Literal["STANDBY", "ACTIVE"] = "STANDBY"
    feed_valve: Literal["ACTIVE", "LOCKED"] = "ACTIVE"
    feed_rate_pct: float = 100.0


class TankState(BaseModel):
    """Full snapshot returned by GET /api/state and pushed over SSE."""

    fsm_state: str
    telemetry: Telemetry
    vision: VisionAssessment | None = None
    context: AmbientContext | None = None
    toxicity: ToxicityAssessment | None = None
    risks: list[RiskAssessment] = Field(default_factory=list)
    hardware: HardwareState = Field(default_factory=HardwareState)
    sensor_fault: bool = False
    system_on: bool = True  # master power — False ⇒ not tracking, logs halted
    power_w: float = 0.0    # instantaneous site draw
    energy_wh: float = 0.0  # cumulative electricity consumed (meter)
    updated_at: datetime


# ── Causal graph panel payload ───────────────────────────────────────
class GraphNode(BaseModel):
    id: str
    label: str
    kind: Literal["Sensor", "Parameter", "Risk", "Hardware"]
    state: str = "nominal"  # nominal | elevated | critical | active | locked


class GraphEdge(BaseModel):
    src: str
    dst: str
    rel: str  # MEASURES | INFLUENCES | MITIGATES


class CausalGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# ── Chaos control (admin/demo panel) ────────────────────────────────
class ChaosCommand(BaseModel):
    """Inputs for the Demo Chaos control panel."""

    do: float | None = Field(None, ge=0, le=15)
    ph: float | None = Field(None, ge=0, le=14)
    temp_c: float | None = Field(None, ge=0, le=45)
    sensor_fault: bool = False


class NarratorCommand(BaseModel):
    run: bool
