"""Shared liquidity maths: standardised impulse, state labels, pillar assembly."""
from __future__ import annotations

import numpy as np
import pandas as pd

DIFF_UNITS = {"%", "pp", "net %", "bp", "% of GDP", "pp of GDP"}
# (short, long) change windows in native periods, and periods per year
WINDOWS = {"W": (13, 26, 52), "M": (3, 6, 12), "Q": (1, 2, 4)}
ADD, DRAIN = 0.5, -0.5          # impulse thresholds (z units)
TREND = 0.3                     # change in impulse over one short window that counts as a turn


def basis_for(units: str) -> str:
    return "diff" if units in DIFF_UNITS else "pct"


def _native(s: pd.Series, freq: str) -> tuple[pd.Series, str]:
    s = s.dropna().sort_index()
    if freq == "D":
        return s.resample("W-WED").last().dropna(), "W"
    return s, freq


def impulse(s: pd.Series, freq: str, polarity: int, basis: str = "pct", years: int = 10) -> pd.Series:
    """Direction-and-speed score: z-score of the sign-adjusted short and long changes, averaged.

    z uses a trailing window only (no look-ahead), so history is what the model would have said at the time.
    """
    x, f = _native(s, freq)
    short, long_, ppy = WINDOWS[f]
    zs = []
    for p in (short, long_):
        ch = x.pct_change(p, fill_method=None) * 100 if basis == "pct" else x.diff(p)
        ch = ch * polarity
        roll = ch.rolling(years * ppy, min_periods=3 * ppy)
        zs.append((ch - roll.mean()) / roll.std())
    out = pd.concat(zs, axis=1).mean(axis=1, skipna=False)
    return out.replace([np.inf, -np.inf], np.nan).dropna().clip(-4, 4)


def short_window(freq: str) -> int:
    return WINDOWS["W" if freq == "D" else freq][0]


def state_of(z: float | None) -> str:
    if z is None or np.isnan(z):
        return "n/a"
    return "adding" if z > ADD else "draining" if z < DRAIN else "neutral"


def trend_of(accel: float | None) -> str:
    if accel is None or np.isnan(accel):
        return "n/a"
    return "improving" if accel > TREND else "deteriorating" if accel < -TREND else "stable"


def to_weekly(s: pd.Series, limit_weeks: int = 14) -> pd.Series:
    if s.empty:
        return s
    idx = pd.date_range(s.index[0], s.index[-1] + pd.Timedelta(days=6), freq="W-WED")
    return s.reindex(s.index.union(idx)).ffill(limit=limit_weeks * 7).reindex(idx).dropna()


def core_impulse(ctx, sid: str) -> tuple[pd.Series, dict]:
    ind = ctx.registry[sid]
    summ = ctx.summary(sid)
    s = ctx.s(sid)
    if s.empty:
        return pd.Series(dtype=float), summ
    return impulse(s, ind.freq, ind.polarity, basis_for(ind.units)), summ


def build_pillar(ctx, pid: str, title: str, core_ids: list[str], member_ids: list[str], *, drivers: list[str],
                 transmission: str, classification: str, timing: str, charts: list[dict], extra: dict | None = None,
                 blurb: str = "") -> dict:
    hist, used, cores = [], [], []
    for sid in core_ids:
        imp, summ = core_impulse(ctx, sid)
        cores.append(summ)
        if not imp.empty and summ["freshness"] in ("fresh", "due"):
            hist.append(to_weekly(imp, limit_weeks=16 if ctx.registry[sid].freq == "Q" else 6).rename(sid))
            used.append(sid)
    if hist:
        h = pd.concat(hist, axis=1).ffill(limit=16).dropna(how="all").mean(axis=1)
        h = h[h.index <= pd.Timestamp(ctx.today) + pd.Timedelta(days=6)]
        z = float(h.iloc[-1])
        back = h[h.index <= h.index[-1] - pd.Timedelta(weeks=13)]
        accel = z - float(back.iloc[-1]) if len(back) else None
        fresh = "fresh" if any(c["freshness"] == "fresh" for c in cores if c["id"] in used) else "due"
    else:
        h, z, accel = pd.Series(dtype=float), None, None
        fresh = "stale" if any(c["latest"] is not None for c in cores) else "missing"
    ctx.put(f"IMPULSE_{pid}", h)
    members = [ctx.summary(m) for m in member_ids if m in ctx.registry]
    return {
        "id": pid, "title": title, "blurb": blurb, "core": cores, "core_used": used,
        "impulse": None if z is None else round(z, 2), "accel": None if accel is None else round(accel, 2),
        "state": state_of(z), "trend": trend_of(accel), "freshness": fresh,
        "impulse_history": h, "members": members, "drivers": drivers, "transmission": transmission,
        "classification": classification, "timing": timing, "charts": charts, **(extra or {}),
    }


def fmt_bn(x: float | None) -> str:
    if x is None or np.isnan(x):
        return "n/a"
    sign = "+" if x > 0 else "−" if x < 0 else ""
    return f"{sign}${abs(x):,.0f}bn" if abs(x) < 1000 else f"{sign}${abs(x) / 1000:,.2f}tn"


def fmt_level(x: float | None) -> str:
    if x is None or np.isnan(x):
        return "n/a"
    return f"${x:,.0f}bn" if abs(x) < 1000 else f"${x / 1000:,.2f}tn"


def last_change(s: pd.Series, weeks: int = 13) -> float | None:
    s = s.dropna()
    if s.empty:
        return None
    prior = s[s.index <= s.index[-1] - pd.Timedelta(weeks=weeks)]
    return None if prior.empty else float(s.iloc[-1] - prior.iloc[-1])
