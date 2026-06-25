"""Context Agent (spec §2.3).

Aggregates asynchronous environmental metadata into an organic-load estimate:
ambient conditions (OpenWeather, fetched by the engine) + recent automated
feed mass. The feed history is the key predictor — feeding drives the TAN
that the Causal Agent later splits into toxic NH₃.

Pure functions; the engine supplies the fetched ambient + feed mass.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import AmbientContext

# TAN accumulation model: baseline + linear contribution per gram fed recently.
# Coefficients are demo-calibrated; in production these come from a biofilter
# capacity curve. The absolute number matters less than the *direction*: more
# feed ⇒ more ammonia.
TAN_BASE_MG_L = 0.20
TAN_PER_GRAM_FEED = 0.020  # mg/L TAN per recent gram dispensed


@dataclass(slots=True)
class ContextResult:
    ambient: AmbientContext
    tan_estimate: float
    notes: list[str] = field(default_factory=list)


def estimate_tan(recent_feed_mass_g: float) -> float:
    """Organic-load proxy → Total Ammonia Nitrogen estimate (mg/L)."""
    return TAN_BASE_MG_L + TAN_PER_GRAM_FEED * max(0.0, recent_feed_mass_g)


def build_context(
    ambient: AmbientContext, recent_feed_mass_g: float
) -> ContextResult:
    tan = estimate_tan(recent_feed_mass_g)
    notes = [
        f"[CONTEXT] ambient {ambient.description} "
        f"(air={ambient.air_temp_c}°C) via {ambient.source}.",
        f"[CONTEXT] recent feed={recent_feed_mass_g:.1f}g → "
        f"TAN estimate {tan:.3f} mg/L.",
    ]
    return ContextResult(
        ambient=ambient.model_copy(update={"recent_feed_mass_g": recent_feed_mass_g}),
        tan_estimate=tan,
        notes=notes,
    )
