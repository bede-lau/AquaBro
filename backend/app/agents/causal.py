"""Causal Diagnostics Agent (spec §2.4) — the graph brain.

Maps verified inputs against the biochemical knowledge graph and executes the
math models (spec §3) to forecast risk. Emits a structured intent the Action
Planner consumes. Pure — no I/O, no LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..causal import graph as graph_mod
from ..causal.math_models import (
    HYPoxIA_DO_CRITICAL,
    assess_toxicity,
    toxicity_slope,
)
from ..schemas import RiskAssessment, Telemetry, ToxicityAssessment, VisionAssessment

SEV_RANK = {"INFO": 0, "WARN": 1, "CRITICAL": 2}
RANK_SEV = {v: k for k, v in SEV_RANK.items()}
# A positive toxicity slope is predictive (spec §3.3), but the raw least-squares
# slope jitters on noise; only treat slopes above this as a real climb.
SLOPE_WARN = 0.002  # mg/L per minute


@dataclass(slots=True)
class CausalResult:
    toxicity: ToxicityAssessment
    risks: list[RiskAssessment]
    severity: str  # max active severity (INFO | WARN | CRITICAL)
    notes: list[str] = field(default_factory=list)


def diagnose(
    telemetry: Telemetry,
    vision: VisionAssessment | None,
    tan_estimate: float,
    nh3_history: list[tuple[datetime, float]],
    *,
    sensor_fault: bool = False,
    hypoxia_confirmed: bool = False,
) -> CausalResult:
    """Run all math models + graph reasoning for one tick."""
    do = telemetry.do_level
    ph = telemetry.ph_level
    temp_c = telemetry.temp_c

    slope = toxicity_slope(nh3_history)
    toxicity = assess_toxicity(tan_estimate, ph, temp_c, slope_per_min=slope)
    approaching = toxicity.nh3_mg_l > 0.8 * toxicity.threshold_mg_l

    notes: list[str] = [
        f"[CAUSAL] NH₃ fraction={toxicity.nh3_fraction:.4f} → "
        f"un-ionized {toxicity.nh3_mg_l:.4f} mg/L "
        f"(thr {toxicity.threshold_mg_l}), slope {slope:+.4f}/min.",
    ]

    risks: list[RiskAssessment] = []

    # ── Ammonia toxicity (spec §3.1 / §3.3) ────────────────────────
    if toxicity.toxic:
        sev = "CRITICAL"
        active = True
        ev = (
            f"NH₃ {toxicity.nh3_mg_l:.3f} mg/L > {toxicity.threshold_mg_l} "
            f"(pH {ph:.2f}, T {temp_c:.1f}°C, TAN {tan_estimate:.2f})."
        )
    elif approaching or slope > SLOPE_WARN:
        sev = "WARN"
        active = True
        ev = (
            f"toxicity climbing: NH₃ {toxicity.nh3_mg_l:.3f}, slope {slope:+.4f}/min."
        )
    else:
        sev, active, ev = "INFO", False, "ammonia within safe envelope."

    risks.append(
        RiskAssessment(
            name="Ammonia_Toxicity",
            severity=sev,  # type: ignore[arg-type]
            active=active,
            evidence=ev,
            mitigations=graph_mod.mitigations_for("Ammonia_Toxicity"),
        )
    )

    # ── Hypoxia (spec §3.2) ────────────────────────────────────────
    # A trusted DO ≤ 1.5 is itself CRITICAL — we aerate before visible die-off
    # rather than waiting for vision to confirm (vision is corroboration, not a
    # gate). A faulted probe stays WARN so a dead sensor can't trigger action.
    if do <= HYPoxIA_DO_CRITICAL:
        active = True
        if sensor_fault:
            sev = "WARN"
            ev = f"DO reads {do:.2f} but probe faulted — unconfirmed, no action."
        else:
            sev = "CRITICAL"
            corr = (
                "vision corroborates lethargy." if hypoxia_confirmed
                else "vision unconfirmed — acting on trusted probe (mortality window ≤180s)."
            )
            ev = f"DO {do:.2f} ≤ {HYPoxIA_DO_CRITICAL} mg/L on trusted probe; {corr}"
    elif do < 3.0:
        sev, active, ev = "WARN", True, f"DO {do:.2f} depressed (<3.0)."
    else:
        sev, active, ev = "INFO", False, f"DO {do:.2f} healthy."

    risks.append(
        RiskAssessment(
            name="Hypoxia",
            severity=sev,  # type: ignore[arg-type]
            active=active,
            evidence=ev,
            mitigations=graph_mod.mitigations_for("Hypoxia"),
        )
    )

    # ── Sensor integrity (electrical, not biological) ──────────────
    if sensor_fault:
        risks.append(
            RiskAssessment(
                name="Sensor_Fault",
                severity="WARN",  # type: ignore[arg-type]
                active=True,
                evidence="DO probe short-circuit signature detected.",
                mitigations=["maintenance_alert"],
            )
        )
        notes.append("[CAUSAL] sensor fault flagged — biological risks use last-known-good DO.")

    max_rank = max(
        (SEV_RANK[r.severity] for r in risks if r.active), default=0
    )
    severity = RANK_SEV[max_rank]
    return CausalResult(toxicity=toxicity, risks=risks, severity=severity, notes=notes)
