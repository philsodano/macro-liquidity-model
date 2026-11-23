import numpy as np
import pandas as pd
import pytest

from macro.research import analogues, backtest, lags


def _ar1(n, phi=0.8, seed=0):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + rng.normal()
    return x


def test_lead_lag_recovers_known_lag():
    idx = pd.date_range("1995-01-01", periods=320, freq="MS")
    x = pd.Series(_ar1(320), index=idx)
    rng = np.random.default_rng(1)
    y = x.shift(6) + rng.normal(0, 0.3, 320)
    out = lags.lead_lag(x, y, max_lag=18, n_boot=200)
    assert out["best_lag"] == 6
    assert out["ci"][0] <= 6 <= out["ci"][1]
    assert out["corr"] > 0.8 and out["n"] > 250


def test_lead_lag_short_series_returns_none():
    idx = pd.date_range("2020-01-01", periods=20, freq="MS")
    out = lags.lead_lag(pd.Series(np.arange(20.0), index=idx), pd.Series(np.arange(20.0), index=idx))
    assert out["best_lag"] is None


def _features():
    idx = pd.date_range("1990-01-01", "2026-10-01", freq="MS")
    rng = np.random.default_rng(3)
    return pd.DataFrame({c: _ar1(len(idx), 0.95, seed=i) for i, c in enumerate("abcd")}, index=idx).add(rng.normal(0, .01, (len(idx), 4)))


def test_nearest_excludes_adjacent_months():
    f = _features()
    target = pd.Timestamp("2026-10-01")
    out = analogues.nearest(f, target, k=5, exclude_months=24)
    dates = [pd.Timestamp(o["date"]) for o in out]
    assert len(out) == 5
    assert all(abs((d - target).days) > 24 * 30 for d in dates)
    for i, a in enumerate(dates):
        for b in dates[i + 1:]:
            assert abs((a - b).days) > 360
    assert out[0]["distance"] <= out[-1]["distance"]


def test_named_regimes_complete():
    f = _features()
    out = analogues.named_regimes(f, pd.Timestamp("2026-10-01"))
    names = [r["name"] for r in out]
    assert len(out) == 7 and "2008 financial crisis" in names and "2022 tightening" in names
    for r in out:
        for k in ("date", "distance", "similar", "different", "why_relevant"):
            assert k in r


def test_conditional_returns_and_hit_rate():
    idx = pd.date_range("2000-01-01", periods=200, freq="MS")
    sig = pd.Series(np.sin(np.arange(200) / 6), index=idx)
    fwd = sig * 10  # perfectly aligned
    out = backtest.conditional_returns(sig, fwd, th=0.5)
    assert out["hit_rate"] == pytest.approx(100.0)
    assert out["mean_when_positive"] > 0 > out["mean_when_negative"]


def test_failure_episodes_grouped():
    idx = pd.date_range("2000-01-01", periods=60, freq="MS")
    sig = pd.Series(1.0, index=idx)
    fwd = pd.Series(5.0, index=idx)
    fwd.iloc[10:14] = -20
    fwd.iloc[40:42] = -15
    eps = backtest.failure_episodes(sig, fwd, th=0.5, bad=-10)
    assert len(eps) == 2 and eps[0]["start"] == "2000-11"


def test_hit_rate_uses_excess_returns():
    idx = pd.date_range("2000-01-01", periods=200, freq="MS")
    sig = pd.Series(np.sin(np.arange(200) / 6), index=idx)
    fwd = sig * 3 + 8  # always positive returns, but higher when signal is positive
    out = backtest.conditional_returns(sig, fwd, th=0.5)
    assert out["hit_rate_excess"] == pytest.approx(100.0)
    assert out["hit_rate"] < 80


def test_lead_lag_expected_sign_ignores_reverse_causality():
    idx = pd.date_range("1990-01-01", periods=360, freq="MS")
    x = pd.Series(_ar1(360, 0.9, 5), index=idx)
    rng = np.random.default_rng(2)
    y = -1.0 * x + 0.6 * x.shift(12) + rng.normal(0, 0.2, 360)  # strong same-month negative, weaker positive at 12
    out = lags.lead_lag(x, y, max_lag=18, n_boot=100, expected_sign=1)
    assert out["best_lag"] >= 6 and out["corr"] > 0
