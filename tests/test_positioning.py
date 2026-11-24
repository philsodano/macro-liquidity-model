from datetime import date

import pandas as pd
import pytest

from macro.analytics import positioning
from macro.context import Ctx
from macro.registry import load_registry, load_settings
from macro.store import Store


def test_ls_ratio_zero_short():
    assert positioning.ls_ratio(300.0, 0.0) is None
    assert positioning.ls_ratio(300.0, 100.0) == pytest.approx(3.0)


def test_net_exposure_formula():
    assert positioning.net_exposure(300.0, 100.0) == pytest.approx(50.0)
    assert positioning.net_exposure(0.0, 0.0) is None


def _ctx(tmp_path, today=date(2026, 11, 24)):
    return Ctx(Store(tmp_path), load_registry(), today=today, settings=load_settings())


def test_positioning_with_no_data(tmp_path):
    out = positioning.assess(_ctx(tmp_path))
    for block in ("hedge_funds", "futures", "leverage", "banks", "options"):
        assert out[block], block
        assert all(i["value"] is None for i in out[block])
    assert all(s.available is False for s in out["signals"])
    assert {s.id for s in out["signals"]} == {"crowding", "fragility", "hedging"}


def test_form_pf_labelled_with_quarter(tmp_path):
    st = Store(tmp_path)
    q = pd.date_range("2022-03-31", "2026-06-30", freq="QE")
    st.write("HF_EQ_LONG", pd.Series(3000.0, index=q), date(2026, 11, 20))
    st.write("HF_EQ_SHORT", pd.Series(1500.0, index=q), date(2026, 11, 20))
    out = positioning.assess(Ctx(st, load_registry(), today=date(2026, 11, 24), settings=load_settings()))
    item = next(i for i in out["hedge_funds"] if i["id"] == "HF_NET_EXPOSURE")
    assert item["period"] == "2026 Q2" and item["value"] == pytest.approx(33.33, abs=0.01)
    assert "months old" in item["plain"]


def test_hedging_inverted_curve_is_headwind(tmp_path):
    st = Store(tmp_path)
    d = pd.bdate_range("2023-01-02", "2026-11-23")
    st.write("VIXCLS", pd.Series(20.0, index=d).where(d < "2026-11-20", 32.0), date(2026, 11, 24))
    st.write("VXVCLS", pd.Series(22.0, index=d).where(d < "2026-11-20", 29.0), date(2026, 11, 24))
    out = positioning.assess(Ctx(st, load_registry(), today=date(2026, 11, 24), settings=load_settings()))
    hedging = next(s for s in out["signals"] if s.id == "hedging")
    assert hedging.available and hedging.score < -0.5
