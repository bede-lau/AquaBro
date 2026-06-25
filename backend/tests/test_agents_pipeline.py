from datetime import datetime, timezone

from app.agents import action, causal
from app.schemas import HardwareState, Telemetry, VisionAssessment

NOW = lambda: datetime.now(timezone.utc)


def _tel(do, ph, temp):
    return Telemetry(timestamp=NOW(), do_level=do, ph_level=ph, temp_c=temp)


def test_ph_spike_drives_feed_lock():
    vision = VisionAssessment(activity_index=0.4, lethargy=False, surface_piping=False,
                              fish_count=30, mean_depth_norm=0.5)
    res = causal.diagnose(_tel(6.0, 8.7, 29.0), vision, tan_estimate=0.5, nh3_history=[])
    assert res.severity == "CRITICAL"
    assert res.toxicity.toxic is True

    plan = action.plan(res, HardwareState(feed_rate_pct=100.0))
    assert plan.feed_valve == "LOCKED"
    assert plan.feed_rate_pct == 50.0
    assert any(w["device"] == "feed_valve" for w in plan.webhooks)


def test_confirmed_hypoxia_drives_aerator_and_voice():
    lethargic = VisionAssessment(activity_index=0.05, lethargy=True, surface_piping=True,
                                 fish_count=30, mean_depth_norm=0.1)
    res = causal.diagnose(_tel(1.2, 7.2, 28.0), lethargic, tan_estimate=0.2, nh3_history=[],
                          hypoxia_confirmed=True)
    assert res.severity == "CRITICAL"

    plan = action.plan(res, HardwareState())
    assert plan.aerator == "ACTIVE"
    assert plan.voice_prompt is not None
    assert plan.telegram_text is not None


def test_baseline_no_action():
    vision = VisionAssessment(activity_index=0.5, lethargy=False, surface_piping=False,
                              fish_count=30, mean_depth_norm=0.5)
    res = causal.diagnose(_tel(6.6, 7.2, 28.4), vision, tan_estimate=0.2, nh3_history=[])
    assert res.severity == "INFO"
    plan = action.plan(res, HardwareState())
    assert plan.aerator is None and plan.feed_valve is None


def test_feed_restores_when_toxicity_clears():
    # valve currently locked, but ammonia no longer active → restore
    vision = VisionAssessment(activity_index=0.5, lethargy=False, surface_piping=False,
                              fish_count=30, mean_depth_norm=0.5)
    res = causal.diagnose(_tel(6.6, 7.2, 28.4), vision, tan_estimate=0.2, nh3_history=[])
    plan = action.plan(res, HardwareState(feed_valve="LOCKED", feed_rate_pct=50.0))
    assert plan.feed_valve == "ACTIVE"
    assert plan.feed_rate_pct == 100.0
