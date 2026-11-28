"""Signals: the unit of evidence. score > 0 supports risk assets / the bull case; < 0 supports the bear case."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import pandas as pd

GROUPS = ("liquidity", "credit", "jobs_report", "growth", "labour", "consumer", "inflation", "policy", "valuation", "positioning")


def score_from_z(z: float | None, scale: float = 1.0) -> float:
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return 0.0
    return float(max(-2.0, min(2.0, z / scale)))


@dataclass
class Signal:
    id: str
    label: str
    score: float
    evidence: str
    kind: str = "fact"          # fact | estimate | interpretation | hypothesis
    horizon: str = "coincident"  # leading | coincident | lagging
    group: str = "growth"
    available: bool = True
    inputs: tuple = ()
    state: str = field(init=False)

    def __post_init__(self):
        self.score = round(max(-2.0, min(2.0, float(self.score))), 2)
        self.state = "positive" if self.score > 0.5 else "negative" if self.score < -0.5 else "neutral"

    def to_dict(self) -> dict:
        return asdict(self)


def missing(id: str, label: str, group: str, why: str) -> Signal:
    return Signal(id=id, label=label, score=0.0, evidence=f"No data: {why}", kind="fact", group=group, available=False)


def chg_z(s: pd.Series, periods: int, years: int = 10, pct: bool = True) -> float | None:
    """z-score of the latest `periods` change against its own trailing history."""
    s = s.dropna()
    if len(s) < periods * 3:
        return None
    ch = s.pct_change(periods, fill_method=None) * 100 if pct else s.diff(periods)
    ch = ch.dropna()
    w = ch[ch.index >= ch.index[-1] - pd.DateOffset(years=years)]
    sd = w.std()
    return None if not sd or math.isnan(sd) else float((ch.iloc[-1] - w.mean()) / sd)


def level_z(s: pd.Series, years: int = 10) -> float | None:
    s = s.dropna()
    if len(s) < 10:
        return None
    w = s[s.index >= s.index[-1] - pd.DateOffset(years=years)]
    sd = w.std()
    return None if not sd or math.isnan(sd) else float((s.iloc[-1] - w.mean()) / sd)
