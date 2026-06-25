from datetime import datetime, timedelta

from app.causal.math_models import (
    NH3_THRESHOLD,
    assess_toxicity,
    pka_ammonia,
    reduced_feed_rate,
    toxicity_slope,
    unionized_nh3_fraction,
)


def test_pka_at_25c_matches_reference():
    assert abs(pka_ammonia(25.0) - 9.245) < 0.01


def test_pka_falls_with_temperature():
    # warmer water → lower pKa → more toxic fraction
    assert pka_ammonia(30.0) < pka_ammonia(20.0)


def test_fraction_monotonic_in_ph():
    f_low = unionized_nh3_fraction(7.0, 28.0)
    f_high = unionized_nh3_fraction(9.0, 28.0)
    assert f_low < f_high < 1.0


def test_assess_toxicity_safe_then_toxic_on_ph_spike():
    safe = assess_toxicity(tan=1.0, ph=7.2, temp_c=28.0)
    assert not safe.toxic and safe.nh3_mg_l < NH3_THRESHOLD

    toxic = assess_toxicity(tan=1.0, ph=8.7, temp_c=28.0)
    assert toxic.toxic and toxic.nh3_mg_l > safe.nh3_mg_l * 15


def test_toxicity_slope_detects_climb():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    climbing = [(t0 + timedelta(seconds=60 * i), 0.01 * (i + 1)) for i in range(5)]
    assert toxicity_slope(climbing) > 0

    flat = [(t0 + timedelta(seconds=60 * i), 0.02) for i in range(5)]
    assert abs(toxicity_slope(flat)) < 1e-9

    assert toxicity_slope([]) == 0.0


def test_reduced_feed_rate_halves():
    assert reduced_feed_rate(100.0) == 50.0
    assert reduced_feed_rate(40.0) == 20.0
    assert reduced_feed_rate(0.0) == 0.0
