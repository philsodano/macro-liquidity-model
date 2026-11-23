"""Series arithmetic: changes over horizons, annualised rates, acceleration, z-scores, percentiles, summaries."""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from .freshness import freshness

_OFFSETS = {
    "4w": pd.DateOffset(weeks=4), "13w": pd.DateOffset(weeks=13), "26w": pd.DateOffset(weeks=26),
    "52w": pd.DateOffset(weeks=52), "1m": pd.DateOffset(months=1), "3m": pd.DateOffset(months=3),
    "6m": pd.DateOffset(months=6), "12m": pd.DateOffset(months=12), "24m": pd.DateOffset(months=24),
}
HORIZONS = {"D": ["4w", "13w", "26w", "52w"], "W": ["4w", "13w", "26w", "52w"],
            "M": ["1m", "3m", "6m", "12m"], "Q": ["3m", "6m", "12m", "24m"]}
PRIMARY = {"D": "13w", "W": "13w", "M": "3m", "Q": "6m"}
_PERIODS_PER_YEAR = {"D": 252, "W": 52, "M": 12, "Q": 4}


def _clean(s: pd.Series) -> pd.Series:
    if s is None or s.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    return s.dropna().sort_index()


def _value_at(s: pd.Series, when: pd.Timestamp, max_gap: pd.Timedelta | None = None) -> float | None:
    """Last observation at or before `when` (None if none, or if it is older than max_gap before `when`)."""
    sub = s[s.index <= when]
    if sub.empty:
        return None
    if max_gap is not None and when - sub.index[-1] > max_gap:
        return None
    return float(sub.iloc[-1])


def _base(s: pd.Series, horizon: str, end: pd.Timestamp | None = None) -> tuple[float, float] | None:
    s = _clean(s)
    if s.empty:
        return None
    end = end if end is not None else s.index[-1]
    now = _value_at(s, end)
    off = _OFFSETS[horizon]
    gap = pd.Timedelta(days=max(10, int(((end - (end - off)).days) * 0.5)))
    then = _value_at(s, end - off, max_gap=gap)
    if now is None or then is None or s.index[0] > end - off:
        return None
    return now, then


def change(s: pd.Series, horizon: str, end: pd.Timestamp | None = None) -> float | None:
    b = _base(s, horizon, end)
    return None if b is None else b[0] - b[1]


def pct_change(s: pd.Series, horizon: str, end: pd.Timestamp | None = None) -> float | None:
    b = _base(s, horizon, end)
    if b is None or b[1] == 0 or (b[0] < 0) != (b[1] < 0):
        return None
    return (b[0] / b[1] - 1) * 100


def acceleration(s: pd.Series, horizon: str) -> float | None:
    """Change over the latest horizon minus change over the horizon before it."""
    s = _clean(s)
    if s.empty:
        return None
    now = change(s, horizon)
    prior = change(s, horizon, end=s.index[-1] - _OFFSETS[horizon])
    return None if now is None or prior is None else now - prior


def ann_rate(s: pd.Series, months: int) -> pd.Series:
    """Annualised % growth over `months` for a monthly series."""
    s = _clean(s)
    base = s.reindex(s.index - pd.DateOffset(months=months))  # by date, so a missing month never shifts the window
    return pd.Series(((s.values / base.values) ** (12 / months) - 1) * 100, index=s.index)


def yoy(s: pd.Series) -> pd.Series:
    """% change from a year earlier, aligned by date (works for any frequency)."""
    s = _clean(s)
    prev = s.reindex(s.index - pd.DateOffset(years=1), method="ffill", tolerance=pd.Timedelta(days=20))
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (s.values / prev.values - 1) * 100
    return pd.Series(out, index=s.index).replace([np.inf, -np.inf], np.nan)


def zscore(s: pd.Series, years: int = 10) -> pd.Series:
    s = _clean(s)
    if s.empty:
        return s
    window = s[s.index >= s.index[-1] - pd.DateOffset(years=years)]
    sd = window.std()
    return (s - window.mean()) / sd if sd and not math.isnan(sd) else s * np.nan


def percentile(s: pd.Series, years: int = 20) -> float | None:
    s = _clean(s)
    if s.empty:
        return None
    w = s[s.index >= s.index[-1] - pd.DateOffset(years=years)]
    return float((w <= w.iloc[-1]).mean() * 100)


def to_period(s: pd.Series, freq: str, how: str = "last") -> pd.Series:
    rule = {"W": "W-WED", "M": "ME", "Q": "QE"}[freq]
    r = _clean(s).resample(rule)
    return (r.last() if how == "last" else r.mean()).dropna()


def direction(s: pd.Series, horizon: str) -> str:
    s = _clean(s)
    c = change(s, horizon)
    if c is None:
        return "n/a"
    hist = s.diff(max(1, len(s[s.index > s.index[-1] - _OFFSETS[horizon]]))).abs().dropna()
    scale = float(hist.median()) if len(hist) > 5 else abs(c)
    if scale == 0 or abs(c) < 0.15 * scale:
        return "flat"
    return "up" if c > 0 else "down"


def period_label(obs_date: str | None, freq: str) -> str:
    if not obs_date:
        return "n/a"
    d = pd.Timestamp(obs_date)
    if freq == "Q":
        return f"{d.year} Q{d.quarter}"
    if freq == "M":
        return d.strftime("%b %Y")
    return f"{d.day} {d.strftime('%b %Y')}"


def ordinal(n: float) -> str:
    n = int(round(n))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _r(x, nd=3):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


def summarize(ind, s: pd.Series, today: date, first_seen: pd.Series | None = None,
              grace: dict | None = None) -> dict:
    s = _clean(s)
    s = s[s.index <= pd.Timestamp(today)]
    meta = {"id": ind.id, "name": ind.name, "short": ind.short or ind.name, "units": ind.units, "source": ind.source,
            "source_id": ind.source_id, "freq": ind.freq, "signal": ind.signal, "kind": ind.kind,
            "polarity": ind.polarity, "what": ind.what, "why": ind.why, "display_only": ind.display_only,
            "pillar": ind.pillar, "role": ind.role, "section": ind.section}
    if s.empty:
        return {**meta, "latest": None, "obs_date": None, "first_seen": None, "changes": {}, "pct_changes": {},
                "accel": None, "z": None, "pctile": None, "direction": "n/a", "yoy": None,
                "freshness": "missing" if not ind.unavailable else "unavailable", "note": ind.unavailable}
    last = s.index[-1]
    fs = None
    if first_seen is not None and not first_seen.empty and last in first_seen.index:
        fs = pd.Timestamp(first_seen.loc[last]).strftime("%Y-%m-%d")
    hz = HORIZONS[ind.freq]
    yo = yoy(s)
    return {
        **meta,
        "latest": _r(s.iloc[-1], 4),
        "obs_date": last.strftime("%Y-%m-%d"),
        "period": period_label(last.strftime("%Y-%m-%d"), ind.freq),
        "first_seen": fs,
        "changes": {h: _r(change(s, h)) for h in hz},
        "pct_changes": {h: _r(pct_change(s, h), 2) for h in hz},
        # latest computable y/y — a missing base month (e.g. Oct-2025 CPI, never published) is not filled in
        "yoy": _r(yo.dropna().iloc[-1], 2) if len(yo.dropna()) else None,
        "yoy_date": yo.dropna().index[-1].strftime("%Y-%m-%d") if len(yo.dropna()) else None,
        "accel": _r(acceleration(s, PRIMARY[ind.freq])),
        "z": _r(zscore(s).iloc[-1], 2),
        "pctile": _r(percentile(s), 1),
        "pctile_years": _r(min(20.0, (last - s.index[0]).days / 365.25), 1),
        "direction": direction(s, PRIMARY[ind.freq]),
        "freshness": freshness(ind, last.date(), today, grace),
        "note": ind.unavailable,
    }


def usable(summary: dict) -> bool:
    return summary.get("freshness") in ("fresh", "due")
