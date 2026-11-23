"""Historical analogues: which past months looked most like today, and what happened next."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..transforms import yoy
from .lags import _monthly

FEATURES = {
    "ff_12m": "Fed funds, 12m change (pp)", "real_ff": "Real fed funds (%)", "curve": "Yield curve 10y−3m (pp)",
    "money_yoy": "M2 growth, y/y (%)", "fed_bs_yoy": "Fed balance sheet, y/y (%)", "baa": "Baa spread (%)",
    "baa_6m": "Baa spread, 6m change (pp)", "unemp_6m": "Unemployment, 6m change (pp)", "core_pce": "Core PCE, y/y (%)",
    "ip_yoy": "Industrial output, y/y (%)",
}
NAMED = [
    ("1994 tightening", "1994-11-01", "Fed doubled rates in a year; bond rout, no recession — a soft landing."),
    ("1998 liquidity rescue", "1998-10-01", "LTCM/Russia crisis; Fed cut three times and markets rebounded."),
    ("2000–02 tech bust", "2000-10-01", "Tight policy into a capex boom (internet); equities fell for two years."),
    ("2008 financial crisis", "2008-09-01", "Credit collapse; Fed flooded the system, but only after deep losses."),
    ("2018 quantitative tightening", "2018-12-01", "QT plus hikes drained liquidity; Q4 sell-off forced a Fed pivot."),
    ("2020 pandemic stimulus", "2020-06-01", "Record fiscal and monetary easing; risk assets soared."),
    ("2022 tightening", "2022-06-01", "Fastest hikes in 40 years plus QT; stocks and bonds fell together."),
]


def raw_features(ctx) -> pd.DataFrame:
    s, has = ctx.s, ctx.has
    cols = {}
    if has("DFF"):
        ff = _monthly(s("DFF"))
        cols["ff_12m"] = ff.diff(12)
        if has("PCEPILFE"):
            cols["real_ff"] = ff - _monthly(yoy(s("PCEPILFE")), "last")
    if has("T10Y3M"):
        cols["curve"] = _monthly(s("T10Y3M"))
    if has("M2SL"):
        cols["money_yoy"] = _monthly(yoy(s("M2SL")), "last")
    if has("WALCL"):
        cols["fed_bs_yoy"] = _monthly(yoy(s("WALCL")))
    if has("BAA10Y"):
        b = _monthly(s("BAA10Y"))
        cols["baa"], cols["baa_6m"] = b, b.diff(6)
    if has("UNRATE"):
        cols["unemp_6m"] = _monthly(s("UNRATE"), "last").diff(6)
    if has("PCEPILFE"):
        cols["core_pce"] = _monthly(yoy(s("PCEPILFE")), "last")
    if has("INDPRO"):
        cols["ip_yoy"] = _monthly(yoy(s("INDPRO")), "last")
    df = pd.DataFrame(cols)
    return df[df.index >= "1986-01-01"]


def standardise(df: pd.DataFrame) -> pd.DataFrame:
    return (df - df.mean()) / df.std()


def _distance(f: pd.DataFrame, target: pd.Timestamp) -> pd.Series:
    t = f.loc[target]
    d = (f - t) ** 2
    valid = d.notna().sum(axis=1)
    out = np.sqrt(d.sum(axis=1) / valid.replace(0, np.nan))
    return out[valid >= max(3, int(t.notna().sum() * 0.6))]


def nearest(f: pd.DataFrame, target: pd.Timestamp, k: int = 5, exclude_months: int = 24, spacing_months: int = 12) -> list[dict]:
    d = _distance(f, target).drop(target, errors="ignore")
    d = d[(d.index < target - pd.DateOffset(months=exclude_months)) | (d.index > target + pd.DateOffset(months=exclude_months))]
    picked = []
    for date, dist in d.sort_values().items():
        if all(abs((date - p).days) > spacing_months * 30 for p, _ in picked):
            picked.append((date, dist))
        if len(picked) == k:
            break
    return [{"date": p.strftime("%Y-%m-%d"), "distance": round(float(v), 2)} for p, v in picked]


def _compare(f: pd.DataFrame, a: pd.Timestamp, b: pd.Timestamp) -> tuple[list[str], list[str]]:
    diff = (f.loc[a] - f.loc[b]).abs().dropna().sort_values()
    name = lambda c: FEATURES.get(c, c)  # noqa: E731
    return [name(c) for c in diff.index[:3]], [name(c) for c in diff.index[::-1][:3]]


def named_regimes(f: pd.DataFrame, target: pd.Timestamp) -> list[dict]:
    d = _distance(f, target) if target in f.index else pd.Series(dtype=float)
    out = []
    for name, date, why in NAMED:
        ts = pd.Timestamp(date)
        sim, dif = _compare(f, ts, target) if ts in f.index and target in f.index else ([], [])
        out.append({"name": name, "date": date, "distance": None if ts not in d.index else round(float(d.loc[ts]), 2),
                    "similar": sim, "different": dif, "why_relevant": why})
    return out


def outcomes(ctx, date: str, spx: pd.Series | None) -> dict:
    t = pd.Timestamp(date)
    t12 = t + pd.DateOffset(months=12)
    o = {}
    def at(s, when):
        s = s.dropna()
        sub = s[s.index <= when]
        return None if sub.empty or when > s.index[-1] else float(sub.iloc[-1])
    if spx is not None and not spx.empty:
        a, b = at(spx, t), at(spx, t12)
        o["stocks_12m_pct"] = None if a is None or b is None else round((b / a - 1) * 100, 1)
    for sid, key in (("BAA10Y", "baa_change_pp"), ("DGS10", "ten_year_change_pp"), ("UNRATE", "unemployment_change_pp")):
        if ctx.has(sid):
            m = _monthly(ctx.s(sid))
            a, b = at(m, t), at(m, t12)
            o[key] = None if a is None or b is None else round(b - a, 2)
    if ctx.has("USREC"):
        r = ctx.s("USREC")
        w = r[(r.index > t) & (r.index <= t12)]
        o["recession_within_12m"] = None if t12 > r.index[-1] else bool(w.max() > 0) if len(w) else False
    return o


def spliced_spx(ctx) -> pd.Series:
    """Monthly S&P 500: Shiller (to 2024) joined to FRED SP500, rescaled at the overlap."""
    parts = []
    if ctx.has("SHILLER_P"):
        parts.append(ctx.s("SHILLER_P"))
    if ctx.has("SP500"):
        sp = _monthly(ctx.s("SP500"))
        if parts:
            sh = parts[0]
            ov = sh.index.intersection(sp.index)
            if len(ov):
                sp = sp * float((sh.loc[ov] / sp.loc[ov]).median())
                parts = [sh[sh.index < sp.index[0]]]
        parts.append(sp)
    return pd.concat(parts).sort_index() if parts else pd.Series(dtype=float)


def assess(ctx) -> dict:
    raw = raw_features(ctx)
    if raw.empty:
        return {"nearest": [], "named": [], "features": {}}
    spx = spliced_spx(ctx)
    ctx.put("SPX_LONG", spx)
    # target = latest month with most features filled
    filled = raw.notna().sum(axis=1)
    target = filled[filled >= filled.max() - 1].index[-1]
    f = standardise(raw)
    near = nearest(f, target)
    for n in near:
        n["outcomes"] = outcomes(ctx, n["date"], spx)
        n["similar"], n["different"] = _compare(f, pd.Timestamp(n["date"]), target)
    named = named_regimes(f, target)
    for n in named:
        n["outcomes"] = outcomes(ctx, n["date"], spx)
    now = raw.loc[target].round(2).to_dict()
    table = {name: {k: (None if pd.isna(raw.loc[pd.Timestamp(d), k]) else round(float(raw.loc[pd.Timestamp(d), k]), 2))
                    for k in raw.columns} for name, d, _ in NAMED if pd.Timestamp(d) in raw.index}
    table["Now"] = {k: (None if pd.isna(v) else v) for k, v in now.items()}
    outs = [n["outcomes"].get("stocks_12m_pct") for n in near if n["outcomes"].get("stocks_12m_pct") is not None]
    return {"as_of_month": target.strftime("%Y-%m"), "nearest": near, "named": named, "features": FEATURES,
            "comparison_table": table,
            "summary": (f"The {len(near)} closest past months saw stocks {np.median(outs):+.0f}% (median) over the next "
                        f"12 months (range {min(outs):+.0f}% to {max(outs):+.0f}%). History rhymes; it does not repeat."
                        if outs else "Not enough outcome data."),
            "method": "Monthly features standardised over 1986–today; distance = root-mean-square gap across available "
                      "features; months within 2 years of today excluded; one pick per 12-month window."}
