"""Combine pillar impulses without adding incompatible numbers."""
from __future__ import annotations

import math

import pandas as pd

from .common import state_of, to_weekly, trend_of

MARKET = ["central_bank", "global", "private_credit"]   # lead risk assets (weeks–quarters)
ECONOMY = ["fiscal", "banking", "ai_capex"]             # lead growth (2–4 quarters)
SPLIT_NOTE = ("Pillars are grouped by what they lead, as classified before testing: market liquidity (Fed, global, "
              "credit spreads) for risk assets; economy liquidity (deficits, bank lending, AI capex) for growth. "
              "The back-test (Research tab) shows market liquidity lining up with stock returns far better than the "
              "all-pillar average, which the economy pillars dilute.")

RULES = [
    "Pillars are combined as standardised impulses (direction and speed), never by adding dollar amounts.",
    "Dollar totals are shown only where units match: Fed net liquidity, and ECB + BoJ in dollars.",
    "Treasury cash and reverse repo are counted once, inside Fed net liquidity — not again under fiscal.",
    "Bank reserves are shown but not added to net liquidity (they are mostly the same money).",
    "Deposits and M2 are shown but not added to bank credit (they are the other side of the same loans).",
    "Bank loans to private-credit funds count under Bank lending, not Private credit.",
    "The Fed is excluded from Global liquidity because it is already counted in Fed liquidity.",
    "AI capex funded from cash flow or bonds is redistribution, not new liquidity.",
    "Stale pillars are left out of the composite and listed.",
]


def _frame(avail: list[dict]) -> pd.DataFrame:
    """Every pillar carried to the same last week, so the latest row never silently drops a slow pillar."""
    end = max(p["impulse_history"].index[-1] for p in avail if len(p["impulse_history"]))
    return pd.concat([to_weekly(p["impulse_history"], 16, end=end).rename(p["id"]) for p in avail], axis=1)


def _accel(avail: list[dict]) -> float | None:
    acc = [p["accel"] for p in avail if p.get("accel") is not None]
    return sum(acc) / len(acc) if acc else None


def _group(pillars: list[dict], ids: list[str]) -> dict:
    sub = [p for p in pillars if p["id"] in ids]
    avail = [p for p in sub if p.get("freshness") in ("fresh", "due") and p.get("impulse") is not None]
    if not avail:
        return {"members": ids, "composite": None, "accel": None, "state": "n/a", "trend": "n/a",
                "history": pd.Series(dtype=float)}
    frame = _frame(avail)
    hist = frame.mean(axis=1).where(frame.notna().sum(axis=1) >= max(1, math.ceil(len(avail) / 2))).dropna()
    comp = sum(p["impulse"] for p in avail) / len(avail)
    accel = _accel(avail)
    return {"members": ids, "used": [p["id"] for p in avail], "composite": round(comp, 2),
            "accel": None if accel is None else round(accel, 2), "state": state_of(comp), "trend": trend_of(accel),
            "history": hist}


def consolidate(pillars: list[dict]) -> dict:
    avail = [p for p in pillars if p.get("freshness") in ("fresh", "due") and p.get("impulse") is not None]
    excluded = [p["id"] for p in pillars if p not in avail]
    breadth = {"adding": 0, "draining": 0, "neutral": 0}
    for p in avail:
        breadth[state_of(p["impulse"])] += 1
    if not avail:
        return {"composite": None, "accel": None, "state": "n/a", "trend": "n/a", "breadth": breadth,
                "excluded": excluded, "composite_history": pd.Series(dtype=float), "rules": RULES,
                "market": _group(pillars, MARKET), "economy": _group(pillars, ECONOMY), "split_note": SPLIT_NOTE}
    composite = sum(p["impulse"] for p in avail) / len(avail)
    frame = _frame(avail)
    hist = frame.mean(axis=1).where(frame.notna().sum(axis=1) >= math.ceil(len(avail) / 2)).dropna()
    accel = _accel(avail)
    return {
        "composite": round(composite, 2), "accel": None if accel is None else round(accel, 2),
        "state": state_of(composite), "trend": trend_of(accel), "breadth": breadth, "excluded": excluded,
        "composite_history": hist, "pillar_history": frame, "rules": RULES,
        "market": _group(pillars, MARKET), "economy": _group(pillars, ECONOMY), "split_note": SPLIT_NOTE,
    }
