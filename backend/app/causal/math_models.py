"""Biochemical math models (spec §3).

These are the deterministic calculations the system *executes* rather than
asking an LLM to hallucinate. All functions are pure.

References
----------
Emerson K., Russo R.C., Lund R.E., Thurston R.V. (1975), "Aqueous ammonia
equilibrium calculations". pKa(T) and the un-ionized fraction formula are the
industry-standard basis for RAS ammonia-toxicity alarms.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..schemas import ToxicityAssessment


# ── Tunable thresholds (spec §3) ─────────────────────────────────────
NH3_THRESHOLD: float = 0.05  # mg/L un-ionized NH3 → CRITICAL_TOXICITY_ALERT
HYPoxIA_DO_CRITICAL: float = 1.5  # mg/L — hypoxia time-to-mortality gate
HYPoxIA_T_CRITICAL_S: float = 180.0  # seconds to mortality at/under DO gate


def pka_ammonia(temp_c: float) -> float:
    """Ammonia acid-dissociation constant pKa as a function of temperature.

    pKa falls as temperature rises → the toxic (un-ionized) NH3 fraction
    grows with heat. Valid for the 0–40 °C RAS operating range.
    """
    return 0.090186 + 2729.92 / (temp_c + 273.15)


def unionized_nh3_fraction(ph: float, temp_c: float) -> float:
    """Fraction of total ammonia present as toxic un-ionized NH3.

    ``f = 1 / (10^(pKa - pH) + 1)``  (spec §3.1).
    """
    pka = pka_ammonia(temp_c)
    return 1.0 / (10.0 ** (pka - ph) + 1.0)


@dataclass(slots=True)
class ToxicityResult:
    pka: float
    fraction: float
    nh3_mg_l: float
    toxic: bool


def _toxicity_components(tan: float, ph: float, temp_c: float) -> ToxicityResult:
    pka = pka_ammonia(temp_c)
    fraction = 1.0 / (10.0 ** (pka - ph) + 1.0)
    nh3 = fraction * tan
    return ToxicityResult(pka=pka, fraction=fraction, nh3_mg_l=nh3, toxic=nh3 > NH3_THRESHOLD)


def assess_toxicity(
    tan: float, ph: float, temp_c: float, slope_per_min: float = 0.0
) -> ToxicityAssessment:
    """Full NH3 toxicity assessment for the Causal Agent.

    Parameters
    ----------
    tan : Total Ammonia Nitrogen (mg/L) — supplied by the Context Agent as
          an organic-load proxy (rises with recent feeding).
    slope_per_min : rate of change of the un-ionized NH3 magnitude; a
                    positive slope is the predictive signal that trips the
                    feed-valve lock (spec §3.3).
    """
    r = _toxicity_components(tan, ph, temp_c)
    return ToxicityAssessment(
        tan=tan,
        ph=ph,
        temp_c=temp_c,
        pka=r.pka,
        nh3_fraction=r.fraction,
        nh3_mg_l=r.nh3_mg_l,
        threshold_mg_l=NH3_THRESHOLD,
        toxic=r.toxic,
        slope_per_min=slope_per_min,
    )


def toxicity_slope(samples: list[tuple[datetime, float]]) -> float:
    """Least-squares slope (mg/L per minute) over recent NH3 magnitudes.

    Used to detect a positive *trajectory* before the absolute threshold is
    crossed — the "predictive" part of the system. Empty/<2 samples → 0.
    """
    if len(samples) < 2:
        return 0.0
    t0 = samples[0][0].timestamp()
    xs = [s[0].timestamp() - t0 for s in samples]  # seconds
    ys = [s[1] for s in samples]
    n = len(xs)
    sx = sum(xs)
    sy = sum(ys)
    denom = n * sum(x * x for x in xs) - sx * sx
    if denom == 0:
        return 0.0
    slope_per_sec = (n * sum(x * y for x, y in zip(xs, ys)) - sx * sy) / denom
    return slope_per_sec * 60.0  # → per minute


def reduced_feed_rate(current_pct: float) -> float:
    """Feed-valve control (spec §3.3): halve the rate when toxicity climbs."""
    return max(0.0, current_pct * 0.5)
