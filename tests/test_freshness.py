from datetime import date

from macro.freshness import freshness
from macro.registry import Indicator

GRACE = {"D": 5, "W": 10, "M": 25, "Q": 45}


def _ind(freq, lag):
    return Indicator(id="X", name="X", source="fred", source_id="X", units="x", freq=freq, section="t",
                     signal="lagging", polarity=1, release_lag_days=lag)


def test_freshness_states_monthly():
    ind = _ind("M", 35)
    # next obs (Oct) expected ~2026-11-05; due window runs to 2026-11-30
    assert freshness(ind, date(2026, 9, 1), date(2026, 11, 1), GRACE) == "fresh"
    assert freshness(ind, date(2026, 9, 1), date(2026, 11, 10), GRACE) == "due"
    assert freshness(ind, date(2026, 9, 1), date(2026, 12, 20), GRACE) == "stale"
    assert freshness(ind, None, date(2026, 12, 20), GRACE) == "missing"


def test_freshness_daily_weekend_not_stale():
    ind = _ind("D", 1)
    assert freshness(ind, date(2026, 11, 20), date(2026, 11, 23), GRACE) in ("fresh", "due")
