from datetime import datetime, timezone

from app.agents import telemetry
from app.schemas import Telemetry, VisionAssessment

NOW = lambda: datetime.now(timezone.utc)


def healthy_vision():
    return VisionAssessment(activity_index=0.55, lethargy=False, surface_piping=False,
                            fish_count=40, mean_depth_norm=0.55)


def lethargic_vision():
    return VisionAssessment(activity_index=0.06, lethargy=True, surface_piping=True,
                            fish_count=40, mean_depth_norm=0.12)


def test_sensor_short_circuit_not_bio_crash():
    prev = Telemetry(timestamp=NOW(), do_level=6.5, ph_level=7.20, temp_c=28.0)
    raw = Telemetry(timestamp=NOW(), do_level=0.0, ph_level=7.21, temp_c=28.0, is_override=True)
    res = telemetry.verify(raw, prev, healthy_vision())
    assert res.sensor_fault is True
    assert res.hypoxia_confirmed is False
    # last-known-good DO is substituted so downstream reasoning isn't poisoned
    assert res.telemetry.do_level == 6.5


def test_confirmed_hypoxia_with_vision_corroboration():
    prev = Telemetry(timestamp=NOW(), do_level=6.5, ph_level=7.20, temp_c=28.0)
    raw = Telemetry(timestamp=NOW(), do_level=1.2, ph_level=7.20, temp_c=28.0, is_override=True)
    res = telemetry.verify(raw, prev, lethargic_vision())
    assert res.hypoxia_confirmed is True
    assert res.sensor_fault is False


def test_low_do_without_corroboration_holds_at_risk():
    prev = Telemetry(timestamp=NOW(), do_level=6.5, ph_level=7.20, temp_c=28.0)
    raw = Telemetry(timestamp=NOW(), do_level=1.4, ph_level=7.20, temp_c=28.0, is_override=True)
    res = telemetry.verify(raw, prev, healthy_vision())
    assert res.hypoxia_confirmed is False
    assert res.sensor_fault is False


def test_healthy_passthrough():
    prev = Telemetry(timestamp=NOW(), do_level=6.5, ph_level=7.20, temp_c=28.0)
    raw = Telemetry(timestamp=NOW(), do_level=6.7, ph_level=7.18, temp_c=28.0)
    res = telemetry.verify(raw, prev, healthy_vision())
    assert res.sensor_fault is False and res.hypoxia_confirmed is False
    assert res.telemetry.do_level == 6.7
