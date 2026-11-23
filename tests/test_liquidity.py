from datetime import date

import numpy as np
import pandas as pd
import pytest

from macro.context import Ctx
from macro.liquidity import central_bank, consolidate, global_liq
from macro.liquidity.common import impulse
from macro.registry import load_registry
from macro.store import Store

LIQ_INPUTS = {"WALCL", "WTREGEN", "TGA_DAILY", "RRPONTSYD"}


def wed(n, end="2026-11-18"):
    return pd.date_range(end=end, periods=n, freq="W-WED")


def test_net_liquidity_identity():
    idx = wed(3)
    walcl = pd.Series(7000.0, index=idx)
    tga = pd.Series(800.0, index=idx)
    rrp = pd.Series(200.0, index=pd.date_range(idx[0], idx[-1], freq="B"))
    out = central_bank.net_liquidity(walcl, tga, rrp)
    assert (out == 6000.0).all() and list(out.index) == list(idx)


def test_pillars_exclusive_and_complete():
    reg = load_registry()
    pillars = {i.pillar for i in reg.values() if i.pillar}
    for p in pillars:
        assert any(i.role == "core" for i in reg.values() if i.pillar == p), f"{p} has no core series"
    keys = [(i.source, i.source_id) for i in reg.values() if i.role == "core"]
    assert len(keys) == len(set(keys))


def test_tga_counted_once():
    reg = load_registry()
    for i in reg.values():
        if i.id in LIQ_INPUTS:
            assert i.pillar == "central_bank" and i.role != "core"
    assert reg["NETLIQ"].role == "core" and reg["NETLIQ"].pillar == "central_bank"
    assert reg["TGA_DAILY"].display_only


def test_g4_fx_decomposition_sums():
    idx = wed(30)
    rng = np.random.default_rng(1)
    books = {
        "ECB": (pd.Series(6000 + rng.normal(0, 20, 30).cumsum(), index=idx), pd.Series(1.08 + rng.normal(0, .01, 30), index=idx)),
        "BOJ": (pd.Series(750000 + rng.normal(0, 900, 30).cumsum(), index=idx), pd.Series(1 / (150 + rng.normal(0, 2, 30)), index=idx)),
    }
    df = global_liq.balance_sheets_usd(books, horizon_weeks=13)
    last = df.iloc[-1]
    assert last["local_contrib"] + last["fx_contrib"] == pytest.approx(last["usd_change"], abs=1e-6)
    assert df["usd_total"].iloc[-1] == pytest.approx(sum(l.iloc[-1] * f.iloc[-1] for l, f in books.values()))


def _pillar(pid, imp, fresh="fresh"):
    hist = pd.Series(imp, index=wed(60))
    return {"id": pid, "impulse": float(hist.iloc[-1]), "impulse_history": hist, "freshness": fresh, "title": pid}


def test_composite_ignores_stale_pillar():
    out = consolidate.consolidate([_pillar("a", 1.0), _pillar("b", -1.0), _pillar("c", 3.0, "stale")])
    assert out["composite"] == pytest.approx(0.0)
    assert out["excluded"] == ["c"]
    assert out["breadth"] == {"adding": 1, "draining": 1, "neutral": 0}


def _synthetic_turn() -> pd.Series:
    rng = np.random.default_rng(7)
    growth = np.r_[0.001 + rng.normal(0, 0.002, 260), np.full(13, -0.01), np.full(13, 0.015)]
    return pd.Series(5000 * np.cumprod(1 + growth), index=wed(len(growth)))


def test_impulse_detects_turn():
    s = _synthetic_turn()
    imp = impulse(s, freq="W", polarity=1, basis="pct")
    assert imp.iloc[-1] > 1.0                      # strongly adding now
    assert imp.iloc[-14] < -1.0                    # was draining a quarter ago
    assert imp.iloc[-1] - imp.iloc[-14] > 0        # accelerating


def test_central_bank_pillar_on_synthetic_store(tmp_path):
    store, reg = Store(tmp_path), load_registry()
    s = _synthetic_turn()
    seen = date(2026, 11, 20)
    store.write("WALCL", s, seen)
    store.write("WTREGEN", pd.Series(800.0, index=s.index), seen)
    store.write("RRPONTSYD", pd.Series(100.0, index=s.index), seen)
    ctx = Ctx(store, reg, today=date(2026, 11, 23))
    p = central_bank.assess(ctx)
    assert p["state"] == "adding" and p["trend"] == "improving"
    assert p["freshness"] in ("fresh", "due")
    assert "NETLIQ" in ctx.extra_series
    contrib = p["decomposition"]
    assert contrib["fed_assets"] + contrib["tga"] + contrib["rrp"] == pytest.approx(contrib["total"], abs=0.01)


def test_fmt_level_has_no_sign():
    from macro.liquidity.common import fmt_bn, fmt_level
    assert fmt_level(10540) == "$10.54tn" and fmt_level(891) == "$891bn"
    assert fmt_bn(-345) == "−$345bn"


def test_net_liquidity_rrp_gaps_are_zero():
    idx = wed(6)
    walcl = pd.Series(7000.0, index=idx)
    tga = pd.Series(800.0, index=idx)
    rrp = pd.Series([200.0, 150.0], index=[idx[0], idx[5]])  # no operations in between = nothing outstanding
    out = central_bank.net_liquidity(walcl, tga, rrp)
    assert len(out) == 6 and out.iloc[2] == 6200.0 and out.iloc[5] == 6050.0


def test_consolidate_splits_market_and_economy():
    ps = [_pillar("central_bank", 1.0), _pillar("global", 0.6), _pillar("private_credit", -0.4),
          _pillar("fiscal", -1.0), _pillar("banking", -1.0), _pillar("ai_capex", 2.0)]
    out = consolidate.consolidate(ps)
    assert out["market"]["members"] == ["central_bank", "global", "private_credit"]
    assert out["market"]["composite"] == pytest.approx(0.4, abs=0.01)
    assert out["economy"]["composite"] == pytest.approx(0.0, abs=0.01)
    assert out["composite"] == pytest.approx(0.2, abs=0.01)
    assert len(out["market"]["history"]) > 0
