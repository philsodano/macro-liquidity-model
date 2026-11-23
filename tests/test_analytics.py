import numpy as np
import pandas as pd
import pytest

from macro.analytics import allocation, central_banks, cross_asset, cycle
from macro.analytics.signals import Signal, score_from_z


def test_recession_prob_known_values():
    assert cycle.recession_prob(0.0) == pytest.approx(29.7, abs=0.1)
    assert cycle.recession_prob(-1.0) == pytest.approx(54.0, abs=0.1)
    assert cycle.recession_prob(2.0) < 5


def test_cycle_mixed_when_dispersed():
    out = cycle.classify(leading=[2.0, -2.0, 1.8, -1.9], coincident=[0.5, 0.4], inflation_dir=0.1)
    assert out["mixed"] is True
    calm = cycle.classify(leading=[0.8, 0.9, 0.7], coincident=[0.6, 0.5], inflation_dir=-0.3)
    assert calm["mixed"] is False and calm["phase"] == "expansion"


def test_cycle_phases():
    assert cycle.classify([-1.0, -0.8], [0.6, 0.5], 0.0)["phase"] == "late cycle / slowing"
    assert cycle.classify([-1.0, -0.8], [-0.9, -0.6], 0.0)["phase"] == "contraction"
    assert cycle.classify([0.9, 0.8], [-0.9, -0.6], 0.0)["phase"] == "early recovery"


def test_real_rate_uses_core_pce():
    idx = pd.date_range("2024-01-01", periods=24, freq="MS")
    core = pd.Series(100 * 1.03 ** (np.arange(24) / 12), index=idx)
    dff = pd.Series(4.0, index=pd.date_range("2025-06-01", "2025-12-31", freq="D"))
    assert central_banks.real_policy_rate(dff, core) == pytest.approx(1.0, abs=0.01)


def test_cuts_priced_estimate():
    # 1y yield ≈ average policy rate over the next year: 3.5 vs 4.0 now → 2 cuts' worth on average
    assert central_banks.cuts_priced(effr=4.0, y1=3.5) == pytest.approx(2.0)


def test_cross_asset_na_when_missing():
    rows = cross_asset.matrix({"liquidity_trend": 0.5, "hy_change_bp": -20, "spy_3m": None, "rsp_spy_3m": None})
    by = {r["id"]: r for r in rows}
    assert by["credit_vs_liquidity"]["verdict"] == "confirm"
    assert by["breadth"]["verdict"] == "n/a"


def test_cross_asset_divergence():
    rows = cross_asset.matrix({"liquidity_trend": 0.6, "hy_change_bp": 90})
    assert {r["id"]: r for r in rows}["credit_vs_liquidity"]["verdict"] == "diverge"


def test_allocation_covers_all_assets():
    factors = {"liquidity": 0.2, "growth": -0.3, "inflation": 0.1, "real_rates": -0.2, "credit": -0.5,
               "dollar": -0.4, "ai": 1.5}
    out = allocation.assess(factors, valuation={}, context={})
    names = {a["asset"] for a in out["assets"]}
    for need in ["US equities", "International equities", "Small caps", "Growth stocks", "Value stocks",
                 "Government bonds", "Investment-grade credit", "High-yield credit", "Private credit", "Cash",
                 "Gold", "Commodities", "Real assets"]:
        assert need in names
    for a in out["assets"] + out["sectors"]:
        assert -2 <= a["score"] <= 2
        for k in ("thesis", "why", "priced_in", "invalidation", "confirmation", "contributions"):
            assert k in a
    assert len(out["sectors"]) >= 11


def test_signal_score_bounds():
    assert score_from_z(5) == 2 and score_from_z(-5) == -2
    s = Signal(id="x", label="X", score=1.2, evidence="e", kind="fact", horizon="leading", group="growth")
    assert s.state == "positive"


def test_short_history_not_called_well_paid():
    from macro.analytics.markets import verdict_from_pctile
    assert verdict_from_pctile(96, years=3) == "short history"
    assert verdict_from_pctile(96, years=20) == "well paid"
