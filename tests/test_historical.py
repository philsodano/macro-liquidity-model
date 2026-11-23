"""Historical regimes: does the engine flag what actually happened? Runs on the committed data store."""
from datetime import date

import pytest

from macro.context import Ctx
from macro.liquidity import assess_all
from macro.registry import load_registry, load_settings
from macro.store import Store


@pytest.fixture(scope="module")
def run():
    reg, st, se = load_registry(), Store(), load_settings()
    cache = {}

    def _run(d):
        if d not in cache:
            ctx = Ctx(st, reg, today=date(2026, 11, 23), as_of=date.fromisoformat(d), settings=se)
            out = assess_all(ctx)
            cache[d] = (out, {p["id"]: p for p in out["pillars"]})
        return cache[d]
    return _run


def test_2018_qt_drains(run):
    out, p = run("2018-12-31")
    assert p["central_bank"]["state"] == "draining"
    assert out["consolidated"]["market"]["composite"] < -0.5
    assert not any("Reverse repo" in s for s in p["central_bank"]["stress"])  # RRP was not a buffer before 2021


def test_2019_repo_stress_flagged(run):
    _, p = run("2019-09-30")
    assert any("repo" in s.lower() for s in p["central_bank"]["stress"])


def test_2020_flood_detected(run):
    out, p = run("2020-04-30")
    assert p["central_bank"]["impulse"] > 2 and p["central_bank"]["state"] == "adding"
    assert out["consolidated"]["market"]["trend"] == "improving"


def test_2022_tightening_drains(run):
    out, p = run("2022-06-30")
    assert out["consolidated"]["market"]["composite"] < -0.5
    assert out["consolidated"]["market"]["trend"] == "deteriorating"
    assert p["central_bank"]["state"] == "draining"


def test_2023_bank_stress_reversal(run):
    _, p = run("2023-03-31")
    assert p["central_bank"]["trend"] == "improving"
    assert any("emergency" in s.lower() for s in p["central_bank"]["stress"])


def test_2026_rrp_buffer_gone_flagged(run):
    _, p = run("2026-11-20")
    assert any("Reverse repo" in s for s in p["central_bank"]["stress"])
