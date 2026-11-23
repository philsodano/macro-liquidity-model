"""Regression tests for the final-review findings (each failed before its fix)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from macro import refresh as refresh_mod
from macro.analytics import liquidity_signals
from macro.analytics.signals import Signal
from macro.context import Ctx
from macro.liquidity import ai_capex, central_bank, consolidate, fiscal
from macro.registry import Indicator, load_registry, load_settings
from macro.store import Store


def _hist(end, freq, n, val):
    return pd.Series(val, index=pd.date_range(end=end, periods=n, freq=freq))


# Critical 1 — trend must compare the same set of pillars
def test_consolidate_accel_uses_constant_pillar_set():
    w = {"id": "banking", "impulse": 0.0, "accel": 0.0, "freshness": "fresh", "impulse_history": _hist("2026-11-18", "W-WED", 200, 0.0)}
    q = {"id": "ai_capex", "impulse": 1.0, "accel": 0.0, "freshness": "fresh", "impulse_history": _hist("2026-09-30", "W-WED", 200, 1.0)}
    out = consolidate.consolidate([w, q])
    assert out["accel"] == pytest.approx(0.0, abs=1e-9)
    assert out["composite_history"].iloc[-1] == pytest.approx(0.5)
    assert out["economy"]["accel"] == pytest.approx(0.0, abs=1e-9)


# Important 1 — derived series take freshness from their inputs
def test_derived_freshness_follows_inputs(tmp_path):
    st, reg = Store(tmp_path), load_registry()
    seen = date(2026, 11, 20)
    st.write("MTSDS133FMS", pd.Series(-150.0, index=pd.date_range("2023-01-01", "2026-10-01", freq="MS")), seen)
    st.write("GDP", pd.Series(30000.0, index=pd.date_range("2023-01-01", "2026-07-01", freq="QS")), seen)
    ctx = Ctx(st, reg, today=date(2026, 11, 28), settings=load_settings())
    fiscal.assess(ctx)
    assert ctx.summary("DEFICIT_12M")["freshness"] in ("fresh", "due")


def test_netliq_stale_when_rrp_feed_stops(tmp_path):
    st, reg = Store(tmp_path), load_registry()
    seen = date(2026, 11, 20)
    idx = pd.date_range(end="2026-11-18", periods=300, freq="W-WED")
    st.write("WALCL", pd.Series(7000.0, index=idx), seen)
    st.write("WTREGEN", pd.Series(800.0, index=idx), seen)
    st.write("RRPONTSYD", pd.Series(100.0, index=pd.bdate_range("2020-01-01", "2026-08-01")), seen)
    ctx = Ctx(st, reg, today=date(2026, 11, 23), settings=load_settings())
    central_bank.assess(ctx)
    assert ctx.summary("NETLIQ")["freshness"] == "stale"


# Important 2 — signals built on stale inputs are not counted
def test_stale_signal_marked_unavailable(tmp_path):
    from macro.analytics import apply_freshness
    st, reg = Store(tmp_path), load_registry()
    st.write("PAYEMS", pd.Series(150000.0, index=pd.date_range("2020-01-01", "2025-01-01", freq="MS")), date(2025, 2, 7))
    ctx = Ctx(st, reg, today=date(2026, 11, 23))
    s = apply_freshness([Signal("payrolls", "Jobs", 1.0, "x", inputs=("PAYEMS",))], ctx)[0]
    assert s.available is False and "stale" in s.evidence.lower()


# Important 3 — an empty or older-than-stored result is a failure, not "unchanged"
@pytest.fixture
def one_series(tmp_path, monkeypatch):
    st = Store(tmp_path)
    ind = Indicator(id="A", name="A", source="fred", source_id="A", units="x", freq="W", section="t", signal="leading",
                    polarity=1, release_lag_days=1)
    st.write("A", pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-11-11", "2026-11-18"])), date(2026, 11, 20))
    return st, {"A": ind}, monkeypatch


def test_refresh_empty_result_is_failure(one_series):
    st, reg, mp = one_series
    mp.setattr(refresh_mod, "SOURCES", {"fred": lambda ind, start: pd.Series(dtype=float)})
    rep = refresh_mod.refresh(st, reg, {"refresh_days": {"fred": 0}}, today=date(2026, 11, 23))
    assert rep["A"]["status"] == "failed" and st.meta("A")["last_error"]


def test_refresh_older_than_stored_is_failure(one_series):
    st, reg, mp = one_series
    mp.setattr(refresh_mod, "SOURCES", {"fred": lambda ind, start: pd.Series([1.0], index=pd.to_datetime(["2026-11-11"]))})
    rep = refresh_mod.refresh(st, reg, {"refresh_days": {"fred": 0}}, today=date(2026, 11, 23))
    assert rep["A"]["status"] == "failed"


# Important 4 — historical runs before 2010 must not crash
@pytest.mark.parametrize("d", ["2006-12-29", "2008-09-30"])
def test_as_of_pre_2010_builds(d):
    from macro.snapshot import build_snapshot
    snap = build_snapshot(Store(), load_registry(), load_settings(), today=date(2026, 11, 23), as_of=date.fromisoformat(d),
                          write=False, research=False)
    assert snap["meta"]["as_of"] == d


# Important 5 — scenario evidence counts market liquidity once; pillars are detail only
def test_liquidity_signals_not_double_counted():
    pillars = [{"id": p, "title": p, "impulse": 1.0, "accel": 0.0, "state": "adding", "trend": "stable"}
               for p in ("central_bank", "fiscal", "banking", "private_credit", "global", "ai_capex")]
    liq = {"pillars": pillars, "consolidated": {"composite": 1.0, "accel": 0.0, "trend": "stable", "breadth": {},
           "market": {"composite": 0.4, "accel": 0.0, "trend": "stable"}, "economy": {"composite": 1.5, "accel": 0.0, "trend": "stable"}}}
    sig = liquidity_signals(liq)
    counted = [s for s in sig if s.group != "detail"]
    assert [s.id for s in counted if s.group == "liquidity"] == ["liq_market"]
    assert [s.id for s in counted if s.group == "growth"] == ["liq_economy"]
    assert all(s.group == "detail" for s in sig if s.id.startswith("liq_") and s.id not in ("liq_market", "liq_economy"))


# Important 6 — release lags for monthly series published a month later
def test_registry_lags_audited():
    reg = load_registry()
    assert reg["JPNASSETS"].release_lag_days >= 30
    assert reg["PCOPPUSDM"].release_lag_days >= 35 and reg["PALLFNFINDEXM"].release_lag_days >= 35


# Important 8 — AI funding totals report which firms are covered
def test_ai_funding_reports_debt_coverage():
    t = pd.DataFrame([{"firm": f, "kind": k, "q": pd.Timestamp("2026-09-30"), "v": 10.0}
                      for f in ai_capex.FIRMS for k in ("CAPEX", "OCF")] +
                     [{"firm": f, "kind": "DEBT_ISS", "q": pd.Timestamp("2026-09-30"), "v": 5.0} for f in ("GOOGL", "META", "AMZN")])
    split = ai_capex.ai_funding_split(t)
    assert split["debt_firms"].iloc[-1] == 3


# Minor 1 (re-graded Important) — back-test signals are used only after they would have been published
def test_backtest_signal_lagged_one_month():
    from macro.research.backtest import published
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-01-01", "2020-02-01"]))
    assert list(published(s).index) == list(pd.to_datetime(["2020-02-01", "2020-03-01"]))
