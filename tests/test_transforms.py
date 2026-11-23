from datetime import date

import numpy as np
import pandas as pd
import pytest

from macro import transforms as T
from macro.registry import Indicator


def weekly(values, end="2026-11-18"):
    idx = pd.date_range(end=end, periods=len(values), freq="W-WED")
    return pd.Series(values, index=idx, dtype=float)


def monthly(values, end="2026-10-01"):
    idx = pd.date_range(end=end, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype=float)


def _ind(freq="W", **kw):
    base = dict(id="X", name="X", source="fred", source_id="X", units="USD bn", freq=freq, section="liquidity",
                signal="leading", polarity=1, release_lag_days=1)
    base.update(kw)
    return Indicator(**base)


def test_change_horizons_weekly():
    s = weekly(np.arange(60))
    assert T.change(s, "13w") == 13
    assert T.change(s, "52w") == 52
    assert T.change(s, "4w") == 4


def test_change_insufficient_history_is_none():
    assert T.change(weekly(np.arange(5)), "52w") is None


def test_pct_change():
    s = monthly([100, 110])
    assert T.pct_change(s, "1m") == pytest.approx(10.0)


def test_ann_rate_monthly():
    s = monthly(100 * 1.01 ** np.arange(24))
    assert T.ann_rate(s, 3).iloc[-1] == pytest.approx(12.6825, abs=1e-3)


def test_yoy_monthly():
    s = monthly(100 * 1.01 ** np.arange(24))
    assert T.yoy(s).iloc[-1] == pytest.approx(12.6825, abs=1e-3)


def test_acceleration_sign():
    up_faster = weekly(np.arange(60) ** 2)
    assert T.acceleration(up_faster, "13w") > 0
    slowing = weekly(np.sqrt(np.arange(60)))
    assert T.acceleration(slowing, "13w") < 0


def test_percentile_bounds():
    s = weekly(np.arange(100))
    assert T.percentile(s) == pytest.approx(100.0)
    assert T.percentile(weekly(np.r_[np.arange(99), 50])) < 60


def test_zscore_latest():
    s = weekly(np.r_[np.zeros(50), np.ones(50)])
    z = T.zscore(s, years=10)
    assert z.iloc[-1] > 0


def test_to_period_monthly_last():
    s = weekly(np.arange(10), end="2026-11-18")
    m = T.to_period(s, "M", "last")
    assert m.index[-1] == pd.Timestamp("2026-11-30") and m.iloc[-1] == 9


def test_summary_has_all_metadata_keys():
    s = weekly(np.arange(60))
    out = T.summarize(_ind(), s, today=date(2026, 11, 23))
    for k in ["id", "name", "short", "latest", "obs_date", "first_seen", "changes", "pct_changes", "accel", "z",
              "pctile", "direction", "freshness", "signal", "kind", "units", "source", "freq", "what", "why",
              "polarity", "display_only"]:
        assert k in out, k
    assert out["obs_date"] == "2026-11-18" and out["direction"] == "up" and out["freshness"] in ("fresh", "due")


def test_summary_ignores_future_dated_obs():
    s = monthly(np.arange(30), end="2028-01-01")
    out = T.summarize(_ind("M"), s, today=date(2026, 11, 23))
    assert out["obs_date"] <= "2026-11-23"


def test_summary_of_empty_series_is_missing():
    out = T.summarize(_ind(), pd.Series(dtype=float), today=date(2026, 11, 23))
    assert out["freshness"] == "missing" and out["latest"] is None


def test_stale_input_excluded_from_composite():
    s = weekly(np.arange(60), end="2025-01-01")
    out = T.summarize(_ind(), s, today=date(2026, 11, 23))
    assert out["freshness"] == "stale"
    assert T.usable(out) is False
    assert T.usable(T.summarize(_ind(), weekly(np.arange(60)), today=date(2026, 11, 23))) is True


def test_summary_reports_percentile_window():
    s = weekly(np.arange(156))  # 3 years
    out = T.summarize(_ind(), s, today=date(2026, 11, 23))
    assert out["pctile_years"] == pytest.approx(3.0, abs=0.1)


def test_summary_yoy_skips_missing_base_month_without_interpolating():
    s = monthly(100 * 1.01 ** np.arange(24), end="2026-10-01").drop(pd.Timestamp("2025-10-01"))
    out = T.summarize(_ind("M"), s, today=date(2026, 11, 23))
    assert out["obs_date"] == "2026-10-01"
    assert out["yoy_date"] == "2026-09-01"
    assert out["yoy"] == pytest.approx(12.68, abs=0.01)


def test_ann_rate_is_date_based_with_gaps():
    s = monthly(100 * 1.01 ** np.arange(24), end="2026-10-01").drop(pd.Timestamp("2026-08-01"))
    r = T.ann_rate(s, 3)
    assert r.loc["2026-10-01"] == pytest.approx(12.68, abs=0.01)
    assert r.loc["2026-09-01"] == pytest.approx(12.68, abs=0.01)


def test_period_and_ordinal_labels():
    assert T.period_label("2026-04-01", "Q") == "2026 Q2"
    assert T.period_label("2026-10-01", "M") == "Oct 2026"
    assert T.period_label("2026-11-18", "W") == "18 Nov 2026"
    assert [T.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 96)] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "96th"]
