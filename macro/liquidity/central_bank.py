"""Pillar 1 — Fed liquidity: balance sheet, Treasury cash, reverse repo, reserves, money-market stress."""
from __future__ import annotations

import pandas as pd

from .common import build_pillar, fmt_bn, last_change


def asof_align(s: pd.Series, idx: pd.DatetimeIndex, tolerance_days: int = 6, before_start: float | None = None) -> pd.Series:
    s = s.dropna().sort_index()
    if s.empty:
        return pd.Series(before_start, index=idx, dtype=float)
    left = pd.DataFrame({"d": pd.DatetimeIndex(idx).astype("datetime64[ns]")})
    right = pd.DataFrame({"d": s.index.astype("datetime64[ns]"), "v": s.values})
    out = pd.merge_asof(left, right, on="d", direction="backward",
                        tolerance=pd.Timedelta(days=tolerance_days)).set_index("d")["v"]
    out.index = pd.DatetimeIndex(idx)
    if before_start is not None:
        out[out.index < s.index[0]] = before_start
    return out


def net_liquidity(walcl: pd.Series, tga: pd.Series, rrp: pd.Series) -> pd.Series:
    """WALCL − TGA − ON RRP on Fed balance-sheet Wednesdays (USD bn). RRP before its 2013 launch = 0."""
    idx = walcl.dropna().index.intersection(tga.dropna().index)
    w, t = walcl.reindex(idx), tga.reindex(idx)
    # ON RRP is overnight: FRED lists only days with operations, so a gap means nothing outstanding (= 0)
    r = asof_align(rrp, idx, tolerance_days=5, before_start=0.0).fillna(0.0)
    return (w - t - r).dropna()


def assess(ctx) -> dict:
    walcl, tga, rrp = ctx.s("WALCL"), ctx.s("WTREGEN"), ctx.s("RRPONTSYD")
    nl = ctx.put("NETLIQ", net_liquidity(walcl, tga, rrp)) if not walcl.empty else pd.Series(dtype=float)
    if ctx.has("SOFR") and ctx.has("IORB"):
        ctx.put("SOFR_IORB", (ctx.s("SOFR") - ctx.s("IORB")).dropna() * 100)
    if ctx.has("WSHOSHO"):
        ctx.put("QT_PACE", ctx.s("WSHOSHO").diff(13) / 3)  # 13-week change ≈ 3 months → per month

    decomp, drivers = {}, []
    if len(nl) > 14:
        idx = nl.index
        r = asof_align(rrp, idx, 5, 0.0).fillna(0.0)
        d = lambda x: last_change(x.reindex(idx))  # noqa: E731
        decomp = {"total": d(nl), "fed_assets": d(walcl), "tga": -d(tga), "rrp": -d(r)}
        decomp = {k: round(v, 1) for k, v in decomp.items() if v is not None}
        if len(decomp) == 4:
            parts = sorted(((k, v) for k, v in decomp.items() if k != "total"), key=lambda kv: -abs(kv[1]))
            names = {"fed_assets": "Fed balance sheet", "tga": "Treasury cash", "rrp": "Reverse repo"}
            drivers.append(f"Last 13 weeks: net liquidity {fmt_bn(decomp['total'])}. Biggest driver: "
                           f"{names[parts[0][0]]} ({fmt_bn(parts[0][1])}).")
            drivers.append(" · ".join(f"{names[k]} {fmt_bn(v)}" for k, v in parts))
    stress = []
    sofr_iorb = ctx.extra_series.get("SOFR_IORB", pd.Series(dtype=float))
    if len(sofr_iorb) > 5 and sofr_iorb.tail(5).mean() > 5:
        stress.append(f"Repo rates {sofr_iorb.tail(5).mean():.0f}bp above IORB — reserves getting scarce.")
    if ctx.has("RPONTSYD") and ctx.s("RPONTSYD").tail(5).max() > 10:
        stress.append(f"Standing repo usage {ctx.s('RPONTSYD').tail(5).max():.0f}bn — dealers short of cash.")
    if ctx.has("RRPONTSYD") and ctx.s("RRPONTSYD").iloc[-1] < 50:
        stress.append("Reverse repo near empty: no buffer left to absorb QT or Treasury cash builds.")
    drivers += stress
    charts = [
        {"id": "cb_netliq", "title": "Fed net liquidity", "units": "USD bn", "start": "2015-01-01",
         "series": [{"key": "NETLIQ", "label": "Net liquidity"}, {"key": "WALCL", "label": "Fed balance sheet"}],
         "source": "Federal Reserve H.4.1; NY Fed (via FRED)", "note": "Net liquidity = Fed assets − Treasury cash − reverse repo"},
        {"id": "cb_drains", "title": "What's absorbing Fed liquidity", "units": "USD bn", "start": "2019-01-01",
         "series": [{"key": "WTREGEN", "label": "Treasury cash (TGA)"}, {"key": "RRPONTSYD", "label": "Reverse repo"},
                    {"key": "WRESBAL", "label": "Bank reserves"}], "source": "Federal Reserve H.4.1 (via FRED)"},
        {"id": "cb_stress", "title": "Repo stress: SOFR minus IORB", "units": "bp", "start": "2021-08-01",
         "series": [{"key": "SOFR_IORB", "label": "SOFR − IORB"}], "source": "NY Fed; Federal Reserve (via FRED)",
         "note": "Above zero = reserves no longer abundant"},
    ]
    return build_pillar(
        ctx, "central_bank", "Fed liquidity", ["NETLIQ"],
        ["WALCL", "WSHOSHO", "WRESBAL", "WTREGEN", "TGA_DAILY", "RRPONTSYD", "RPONTSYD", "WLCFLPCL",
         "H41RESPPALDKNWW", "SOFR_IORB", "QT_PACE"],
        blurb="Cash the Fed leaves in the system after Treasury's account and money funds' parked cash.",
        drivers=drivers or ["Not enough data."],
        transmission="Reserves → bank and dealer balance sheets → money-market rates and risk appetite. "
                     "Markets react within weeks; growth effects run through credit over 6–12 months.",
        classification="Creation/destruction. QE creates reserves; QT and Treasury cash builds destroy them. "
                       "Reverse-repo drains release cash that already existed.",
        timing="Leading for risk assets (weeks to a quarter). Weak link to the economy on its own.",
        charts=charts, extra={"decomposition": decomp, "stress": stress})
