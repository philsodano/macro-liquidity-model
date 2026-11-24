"""Fixes from the 2026-11-24 fact-check against outside sources."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from macro import narrative
from macro.analytics import inflation
from macro.registry import load_registry

SNAP = json.loads((Path(__file__).parent.parent / "site" / "snapshot.json").read_text())


def test_sahm_mentions_false_signals():
    why = load_registry()["SAHMREALTIME"].why
    assert "2024" in why and "without" in why


def test_basis_trade_not_blamed_for_april_2025():
    why = load_registry()["HF_TREAS_BASIS"].why
    assert "(March 2020, April 2025)" not in why and "no basis-trade unwind" in why


def test_policy_direction_detects_hikes():
    idx = pd.date_range("2025-11-01", "2026-11-23", freq="D")
    tgt = pd.Series(4.0, index=idx).where(idx >= "2026-09-17", 3.75)
    assert narrative.policy_direction(tgt, cuts_priced=-3.0) == "hiking"
    assert narrative.policy_direction(pd.Series(3.75, index=idx), cuts_priced=2.0) == "on hold, cuts expected"


def test_scenario_text_follows_direction():
    a = {"central_banks": {"direction": "hiking"}}
    t = narrative.fed_lines("hiking", ff=3.88, core=3.1)
    assert "cut" not in t["base"].lower() and "hike" in t["base"].lower()


def test_inflation_direction_uses_freshest_core_measures():
    # core CPI re-accelerating (3m well above y/y), core PCE gently slowing → overall direction is up
    rates = {"PCEPILFE": {"yoy": 3.1, "3m": 2.9}, "CPILFESL": {"yoy": 2.6, "3m": 3.8}}
    assert inflation.direction(rates) > 0
