from datetime import date

import pandas as pd
import pytest

from macro import refresh as refresh_mod
from macro.registry import Indicator
from macro.store import Store


def _ind(i, source="fred"):
    return Indicator(id=i, name=i, source=source, source_id=i, units="x", freq="W", section="t",
                     signal="leading", polarity=1, release_lag_days=1)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = Store(tmp_path)
    reg = {"A": _ind("A"), "B": _ind("B", "treasury"), "D": _ind("D", "derived")}

    def good(ind, start):
        return pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-11-11", "2026-11-18"]))

    def bad(ind, start):
        raise RuntimeError("HTTP 503")

    monkeypatch.setattr(refresh_mod, "SOURCES", {"fred": good, "treasury": bad})
    settings = {"refresh_days": {"fred": 1, "treasury": 7, "derived": 0}, "history_start": "2000-01-01"}
    return store, reg, settings


def test_refresh_survives_failed_source(setup):
    store, reg, settings = setup
    store.write("B", pd.Series([5.0], index=pd.to_datetime(["2026-11-01"])), seen_at=date(2026, 11, 2))
    before = (store.root / "data" / "series" / "B.csv").read_text()
    rep = refresh_mod.refresh(store, reg, settings, today=date(2026, 11, 23))
    assert rep["A"]["status"] == "updated" and rep["A"]["new_obs"] == 2
    assert rep["B"]["status"] == "failed" and "503" in rep["B"]["error"]
    assert (store.root / "data" / "series" / "B.csv").read_text() == before
    assert store.meta("B")["last_error"]


def test_refresh_skips_derived(setup):
    store, reg, settings = setup
    rep = refresh_mod.refresh(store, reg, settings, today=date(2026, 11, 23))
    assert rep["D"]["status"] == "skipped"


def test_refresh_respects_frequency(setup):
    store, reg, settings = setup
    store.set_meta("B", last_fetch="2026-11-22")
    rep = refresh_mod.refresh(store, reg, settings, today=date(2026, 11, 23), only_due=True)
    assert rep["B"]["status"] == "skipped"
    rep = refresh_mod.refresh(store, reg, settings, today=date(2026, 11, 23), only_due=False)
    assert rep["B"]["status"] == "failed"


def test_refresh_unchanged_second_time(setup):
    store, reg, settings = setup
    refresh_mod.refresh(store, reg, settings, today=date(2026, 11, 23), ids=["A"])
    rep = refresh_mod.refresh(store, reg, settings, today=date(2026, 11, 24), ids=["A"])
    assert rep["A"]["status"] == "unchanged"
