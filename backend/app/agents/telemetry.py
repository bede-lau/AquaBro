"""Telemetry Verification Agent (spec §2.1).

Ingests raw IoT streams and cross-references covariant metrics to tell a
sensor short-circuit apart from a real biological crash. This is the
fault-tolerance core: a single DO reading of ~0 with rock-stable pH and no
vision-confirmed lethargy is a *probe fault*, not a fish kill.

Pure function — no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import Telemetry, VisionAssessment

# ── Tunables ─────────────────────────────────────────────────────────
DO_FAULT_FLOOR = 0.5        # DO at/under this with no corroboration ⇒ suspect
DO_HYPOXIA_CRITICAL = 1.5   # spec §3.2
PH_STABLE_DELTA = 0.12      # pH moved less than this ⇒ "rock-stable"
DO_RECOVERY_EPS = 0.25


@dataclass(slots=True)
class VerificationResult:
    telemetry: Telemetry          # verified stream (DO corrected on fault)
    sensor_fault: bool
    hypoxia_confirmed: bool       # DO low AND vision corroborates
    notes: list[str] = field(default_factory=list)


def verify(
    raw: Telemetry,
    prev: Telemetry | None,
    vision: VisionAssessment | None,
) -> VerificationResult:
    """Classify a raw telemetry sample.

    Decision matrix for a DO crash:
      DO ≤ 1.5 + vision lethargy/piping      → confirmed hypoxia (biological)
      DO ≤ 0.5 + pH stable + no lethargy     → SENSOR FAULT (electrical)
      otherwise                              → accept raw reading
    On a fault, the verified stream substitutes the last-known-good DO so
    downstream reasoning isn't poisoned by a dead probe.
    """
    notes: list[str] = []
    sensor_fault = False
    do = raw.do_level
    ph_delta = abs(raw.ph_level - prev.ph_level) if prev else 0.0
    ph_stable = ph_delta < PH_STABLE_DELTA
    lethargic = bool(vision and (vision.lethargy or vision.surface_piping))

    hypoxia_confirmed = do <= DO_HYPOXIA_CRITICAL and lethargic

    # Sensor short-circuit signature: DO dropped to ~0 while pH barely moved
    # and the biomass is acting normally.
    if do <= DO_FAULT_FLOOR and ph_stable and not lethargic:
        sensor_fault = True
        notes.append(
            f"[VERIFY] DO={do:.2f}≈0 but ΔpH={ph_delta:.2f} stable & no "
            f"lethargy → SENSOR SHORT-CIRCUIT, not biological crash."
        )
        if prev is not None:
            do = prev.do_level  # trust last-known-good
            notes.append(f"[VERIFY] substituting last-known-good DO={do:.2f}")

    if hypoxia_confirmed:
        notes.append(
            f"[VERIFY] DO={raw.do_level:.2f}≤{DO_HYPOXIA_CRITICAL} corroborated "
            f"by vision lethargy → CONFIRMED HYPOXIA."
        )
    elif do <= DO_HYPOXIA_CRITICAL and not sensor_fault:
        notes.append(
            f"[VERIFY] DO={do:.2f}≤{DO_HYPOXIA_CRITICAL} but vision unconfirmed "
            f"— holding at risk pending biological ground truth."
        )

    verified = raw.model_copy(update={"do_level": do}) if do != raw.do_level else raw
    return VerificationResult(
        telemetry=verified,
        sensor_fault=sensor_fault,
        hypoxia_confirmed=hypoxia_confirmed,
        notes=notes,
    )
