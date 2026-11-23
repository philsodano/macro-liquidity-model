from datetime import date

import pandas as pd
import pytest

from macro.store import Store


def _s(d: dict) -> pd.Series:
    return pd.Series(list(d.values()), index=pd.to_datetime(list(d.keys())), dtype=float)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_write_then_read_roundtrip(store):
    n = store.write("X", _s({"2026-01-01": 1.0, "2026-02-01": 2.0, "2026-03-01": 3.5}), seen_at=date(2026, 3, 10))
    assert n == 3
    out = store.read("X")
    assert isinstance(out.index, pd.DatetimeIndex)
    assert list(out.values) == [1.0, 2.0, 3.5]


def test_revision_appends_vintage(store):
    store.write("X", _s({"2026-09-01": 100.0}), seen_at=date(2026, 10, 3))
    n = store.write("X", _s({"2026-09-01": 101.0, "2026-10-01": 102.0}), seen_at=date(2026, 11, 7))
    assert n == 2
    vint = pd.read_csv(store.root / "data" / "vintages" / "X.csv")
    assert len(vint) == 3
    assert store.read("X").loc["2026-09-01"] == 101.0


def test_unchanged_rewrite_adds_no_vintage(store):
    store.write("X", _s({"2026-09-01": 100.0}), seen_at=date(2026, 10, 3))
    n = store.write("X", _s({"2026-09-01": 100.0}), seen_at=date(2026, 10, 4))
    assert n == 0
    assert len(pd.read_csv(store.root / "data" / "vintages" / "X.csv")) == 1


def test_write_empty_series_is_noop(store):
    store.write("X", _s({"2026-09-01": 100.0}), seen_at=date(2026, 10, 3))
    before = (store.root / "data" / "series" / "X.csv").read_text()
    assert store.write("X", pd.Series(dtype=float), seen_at=date(2026, 10, 4)) == 0
    assert (store.root / "data" / "series" / "X.csv").read_text() == before


def test_read_as_of_excludes_later_vintages(store):
    store.write("X", _s({"2026-09-01": 100.0}), seen_at=date(2026, 10, 3))
    store.write("X", _s({"2026-09-01": 101.0, "2026-10-01": 102.0}), seen_at=date(2026, 11, 7))
    out = store.read("X", as_of=date(2026, 10, 15))
    assert out.to_dict() == {pd.Timestamp("2026-09-01"): 100.0}


def test_read_missing_returns_empty(store):
    assert store.read("NOPE").empty


def test_meta_roundtrip(store):
    store.set_meta("X", last_fetch="2026-11-23", source="fred")
    store.set_meta("X", last_error=None)
    m = store.meta("X")
    assert m["last_fetch"] == "2026-11-23" and m["source"] == "fred" and "last_error" in m


def test_write_rounds_float_noise(store):
    store.write("X", _s({"2026-01-01": 892310 * 0.001}), seen_at=date(2026, 1, 2))
    assert "892.31\n" in (store.root / "data" / "series" / "X.csv").read_text()
