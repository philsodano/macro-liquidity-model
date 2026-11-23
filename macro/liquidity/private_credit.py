"""Pillar 4 — Private credit & capital markets: the price and availability of non-bank credit."""
from __future__ import annotations

from ..transforms import ordinal

from .common import build_pillar


def drawdown(s) -> float | None:
    s = s.dropna()
    if len(s) < 30:
        return None
    w = s[s.index >= s.index[-1] - __import__("pandas").DateOffset(years=1)]
    return float((w.iloc[-1] / w.max() - 1) * 100)


def assess(ctx) -> dict:
    drivers, extra = [], {}
    for sid, label in (("BAMLH0A0HYM2", "High-yield"), ("BAMLC0A0CM", "Investment-grade"), ("BAA10Y", "Baa")):
        if ctx.has(sid):
            s = ctx.summary(sid)
            ch = s["changes"].get("13w")
            drivers.append(f"{label} spread {s['latest']:.2f}% "
                           f"({'+' if (ch or 0) >= 0 else '−'}{abs((ch or 0) * 100):.0f}bp over 13 weeks; "
                           f"{ordinal(s['pctile'])} percentile of {s['pctile_years']:.0f} years).")
    hy = ctx.summary("BAMLH0A0HYM2") if ctx.has("BAMLH0A0HYM2") else None
    if hy and (hy["changes"].get("13w") or 0) > 0.75:
        drivers.insert(0, f"Warning: high-yield spreads up {hy['changes']['13w'] * 100:.0f}bp in 13 weeks — "
                          "fast widening often comes before broader credit stress.")
        extra["stress"] = True
    if ctx.has("BAMLH0A3HYC") and ctx.has("BAMLH0A0HYM2"):
        gap = ctx.put("CCC_HY_GAP", (ctx.s("BAMLH0A3HYC") - ctx.s("BAMLH0A0HYM2")).dropna())
        extra["ccc_hy_gap"] = round(float(gap.iloc[-1]), 2)
    dd = {}
    for sid in ("BIZD", "ARCC", "BKLN"):
        if ctx.has(sid):
            v = drawdown(ctx.s(sid))
            if v is not None:
                dd[sid] = round(v, 1)
    if dd:
        drivers.append("Private-credit prices vs 1-year high: " + " · ".join(f"{k} {v:+.1f}%" for k, v in dd.items()))
    else:
        drivers.append("No daily private-credit prices (Tiingo key not working) — using public spreads only.")
    extra["drawdowns"] = dd
    if ctx.has("NCBDBIQ027S"):
        s = ctx.summary("NCBDBIQ027S")
        if s["yoy"] is not None:
            drivers.append(f"Corporate bonds outstanding {s['yoy']:+.1f}% y/y ({s['period']}).")
    charts = [
        {"id": "pc_spreads", "title": "Corporate credit spreads", "units": "%", "start": "2000-01-01",
         "series": [{"key": "BAA10Y", "label": "Baa − 10y Treasury"}, {"key": "BAMLH0A0HYM2", "label": "High-yield OAS"},
                    {"key": "BAMLC0A0CM", "label": "Investment-grade OAS"}],
         "source": "Moody's; ICE BofA (via FRED; ICE history limited to ~3 years)"},
        {"id": "pc_bdc", "title": "Private credit prices", "units": "USD (adj.)", "start": "2018-01-01",
         "series": [{"key": "BIZD", "label": "BDC ETF"}, {"key": "BKLN", "label": "Leveraged loans ETF"}],
         "source": "Tiingo"},
    ]
    return build_pillar(
        ctx, "private_credit", "Private credit & bonds", ["BAA10Y"],
        ["BAA10Y", "BAMLH0A0HYM2", "BAMLC0A0CM", "BAMLH0A3HYC", "NCBDBIQ027S", "BCNSDODNS", "COMPOUT", "BIZD", "ARCC",
         "BKLN", "HYG", "LQD", "BX"],
        blurb="Credit from bond markets, private-credit funds and other non-banks. Mostly moves existing savings around.",
        drivers=drivers or ["Not enough data."],
        transmission="Tight spreads and open markets let weaker borrowers refinance; when spreads widen, "
                     "refinancing stops and defaults follow 2–4 quarters later.",
        classification="Mostly redistribution: investors' existing savings are lent on. The bank-funded slice "
                       "(bank loans to nonbank lenders) is counted under Bank lending, not here. Spreads measure "
                       "whether the channel is open.",
        timing="Spreads: leading to coincident. Volumes: lagging.",
        charts=charts, extra=extra)
