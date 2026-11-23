"""Snapshot tests run on the committed data store (offline, deterministic)."""
import json
from datetime import date

import pytest

from macro.registry import load_registry, load_settings
from macro.snapshot import build_snapshot
from macro.store import Store


@pytest.fixture(scope="module")
def snap():
    settings = load_settings()
    settings.setdefault("research", {})["n_boot"] = 30
    return build_snapshot(Store(), load_registry(), settings, today=date(2026, 11, 23), write=False)


def test_snapshot_keys(snap):
    for k in ("schema_version", "meta", "executive", "central_banks", "liquidity", "consumer", "cycle", "inflation",
              "markets", "cross_asset", "allocation", "scenarios", "research", "changes", "data_quality", "series"):
        assert k in snap, k
    assert sum(snap["scenarios"]["final"].values()) == pytest.approx(100, abs=0.1)
    json.dumps(snap)  # fully serialisable


def _walk(o):
    if isinstance(o, dict):
        if "freshness" in o and "source" in o and "obs_date" in o:
            yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def test_every_displayed_metric_has_metadata(snap):
    summaries = list(_walk({k: v for k, v in snap.items() if k != "series"}))
    assert len(summaries) > 100
    for s in summaries:
        if s.get("latest") is None:
            continue
        for k in ("source", "obs_date", "freq", "freshness", "units"):
            assert s.get(k) not in (None, ""), (s.get("id"), k)


def test_chart_series_present_with_units_and_source(snap):
    charts = snap["charts"]
    assert len(charts) > 20
    for c in charts:
        assert c["units"] and c["source"] and c["title"]
        for s in c["series"]:
            assert "data_key" in s


def test_as_of_snapshot_has_no_future_obs():
    settings = load_settings()
    settings.setdefault("research", {})["n_boot"] = 10
    snap = build_snapshot(Store(), load_registry(), settings, today=date(2026, 11, 23), as_of=date(2022, 6, 30),
                          write=False, research=False)
    assert snap["meta"]["mode"] == "as_of"
    for key, pts in snap["series"].items():
        if pts:
            assert pts[-1][0] <= "2022-06-30", key
    for s in _walk({k: v for k, v in snap.items() if k != "series"}):
        if s.get("obs_date"):
            assert s["obs_date"] <= "2022-06-30", s["id"]
