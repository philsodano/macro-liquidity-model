"""Pillar 2 — Fiscal: deficits, fiscal impulse, issuance mix. TGA is counted in the Fed pillar, not here."""
from __future__ import annotations

import pandas as pd

from .common import build_pillar, fmt_bn, fmt_level


def deficit_pct_gdp(mts_bn: pd.Series, gdp_bn_saar: pd.Series) -> pd.Series:
    """Rolling 12-month deficit (positive = deficit) as % of nominal GDP. Needs 12 consecutive months."""
    m = mts_bn.dropna().asfreq("MS")
    deficit = -m.rolling(12, min_periods=12).sum()
    g = gdp_bn_saar.dropna()
    gm = g.reindex(g.index.union(deficit.index)).ffill().reindex(deficit.index)
    return (deficit / gm * 100).dropna()


def assess(ctx) -> dict:
    drivers, extra = [], {}
    if ctx.has("MTSDS133FMS") and ctx.has("GDP"):
        d = ctx.put("DEFICIT_12M", deficit_pct_gdp(ctx.s("MTSDS133FMS"), ctx.s("GDP")))
        fi = ctx.put("FISCAL_IMPULSE", d.diff(12))
        if len(fi):
            drivers.append(f"Deficit {d.iloc[-1]:.1f}% of GDP over the last 12 months; "
                           f"{'up' if fi.iloc[-1] > 0 else 'down'} {abs(fi.iloc[-1]):.1f}pp on a year ago "
                           f"({'more' if fi.iloc[-1] > 0 else 'less'} support).")
    if ctx.has("DEBT_BILLS") and ctx.has("DEBT_TOTAL"):
        bs = ctx.put("BILL_SHARE", (ctx.s("DEBT_BILLS") / ctx.s("DEBT_TOTAL") * 100).dropna())
        bills3 = ctx.s("DEBT_BILLS").diff(3).iloc[-1]
        coupons = (ctx.s("DEBT_COUPONS").add(ctx.s("DEBT_BONDS"), fill_value=0)).diff(3).iloc[-1]
        extra["net_issuance_3m"] = {"bills": round(float(bills3), 1), "coupons": round(float(coupons), 1)}
        drivers.append(f"Net issuance, last 3 months: bills {fmt_bn(bills3)}, notes+bonds {fmt_bn(coupons)}. "
                       f"Bills are {bs.iloc[-1]:.1f}% of marketable debt.")
    if ctx.has("A091RC1Q027SBEA"):
        s = ctx.summary("A091RC1Q027SBEA")
        drivers.append(f"Federal interest costs {fmt_level(s['latest'])} a year (annual rate), "
                       f"{s['yoy']:+.1f}% y/y — income to bondholders.") if s["yoy"] is not None else None
    tga = ctx.summary("TGA_DAILY") if "TGA_DAILY" in ctx.registry else None
    if tga and tga["latest"] is not None:
        drivers.append(f"Treasury cash balance {fmt_level(tga['latest'])} ({tga['obs_date']}) — counted in Fed liquidity.")
    charts = [
        {"id": "fiscal_deficit", "explain": "Blue: how much more the government spent than it collected over the last 12 months, as a share of the economy. Orange: the change versus a year earlier — the 'fiscal impulse'. Bigger deficits put more money into household and business pockets; growth reacts to the change, not the level.", "title": "Federal deficit, rolling 12 months", "units": "% of GDP", "start": "2000-01-01",
         "series": [{"key": "DEFICIT_12M", "label": "Deficit"}, {"key": "FISCAL_IMPULSE", "label": "Change vs year ago"}],
         "source": "US Treasury Monthly Treasury Statement; BEA GDP (via FRED)"},
        {"id": "fiscal_bills", "explain": "The share of government debt in short-term bills. Bills are mostly bought with idle money-fund cash, so funding with bills drains less from markets than long-term bonds. A rising share is quietly supportive for liquidity.", "title": "Share of debt in T-bills", "units": "%", "start": "2005-01-01",
         "series": [{"key": "BILL_SHARE", "label": "Bills ÷ marketable debt"}],
         "source": "US Treasury Monthly Statement of the Public Debt"},
    ]
    return build_pillar(
        ctx, "fiscal", "Government spending", ["DEFICIT_12M"],
        ["DEFICIT_12M", "FISCAL_IMPULSE", "MTSDS133FMS", "PCTR", "A091RC1Q027SBEA", "DEBT_BILLS", "DEBT_COUPONS",
         "DEBT_BONDS", "BILL_SHARE"],
        blurb="How much the government spends beyond what it taxes, and how it funds the gap.",
        drivers=[x for x in drivers if x] or ["Not enough data."],
        transmission="Deficit spending lands as household and business income and deposits. Coupon issuance "
                     "competes for savings and pushes up long yields; bills mostly draw idle money-fund cash.",
        classification="Adds private-sector income and deposits (net financial assets). Funding mix decides "
                       "how much is offset: bills ≈ neutral, coupons absorb duration and deposits.",
        timing="Leading for growth by 2–4 quarters (impulse). Level matters less than the change.",
        charts=charts, extra=extra)
