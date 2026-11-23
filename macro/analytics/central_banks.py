"""B. Central banks: stance (nominal vs real), what markets price, and whether policy is transmitting."""
from __future__ import annotations

import pandas as pd

from ..transforms import yoy
from .signals import Signal, level_z, missing

NEUTRAL_REAL = 0.75   # assumed neutral real fed funds rate (estimate; Fed SEP longer-run 3.0% less 2% ≈ 1%)


def real_policy_rate(dff: pd.Series, core_pce_index: pd.Series) -> float | None:
    if dff.dropna().empty or core_pce_index.dropna().empty:
        return None
    infl = yoy(core_pce_index).dropna()
    return None if infl.empty else float(dff.dropna().iloc[-1] - infl.iloc[-1])


def cuts_priced(effr: float, y1: float) -> float:
    """25bp moves in the AVERAGE policy rate over the next 12 months, reading the 1-year yield as that average.

    Conservative estimate: the 1-year yield also carries term premium and a bill/funds basis, so this is a
    direction-and-size guide, not a futures-implied path (fed funds futures are not freely available)."""
    return (effr - y1) / 0.25


def assess(ctx) -> dict:
    sig, notes, table = [], [], []
    dff, core = ctx.s("DFF"), ctx.s("PCEPILFE")
    rr = real_policy_rate(dff, core)
    effr = float(dff.iloc[-1]) if len(dff) else None
    if rr is not None:
        gap = rr - NEUTRAL_REAL
        ctx.put("REAL_FF", (dff.resample("MS").mean() - yoy(core)).dropna())
        word = "restrictive" if gap > 0.5 else "easy" if gap < -0.5 else "close to neutral"
        sig.append(Signal("real_policy_rate", "Real policy rate", -gap, kind="estimate", horizon="leading", group="policy",
                          evidence=f"Fed funds {effr:.2f}% minus core PCE inflation {effr - rr:.2f}% = {rr:+.2f}% real; "
                                   f"{word} vs an assumed neutral of {NEUTRAL_REAL:.2f}%."))
    else:
        sig.append(missing("real_policy_rate", "Real policy rate", "policy", "fed funds or core PCE missing"))
    if effr is not None and ctx.has("DGS1") and ctx.has("DGS2"):
        y1, y2 = float(ctx.s("DGS1").iloc[-1]), float(ctx.s("DGS2").iloc[-1])
        n = cuts_priced(effr, y1)
        ctx.put("CUTS_PRICED", ((ctx.s("DFF") - ctx.s("DGS1")) / 0.25).dropna())
        verb = "cuts" if n > 0 else "hikes"
        sig.append(Signal("market_path", "Rate path priced by markets", max(-2, min(2, n / 2)), kind="estimate",
                          horizon="leading", group="policy",
                          evidence=f"1-year yield {y1:.2f}% vs fed funds {effr:.2f}%: markets see the average policy rate "
                                   f"over the next year {abs(effr - y1):.2f}pp {'lower' if n > 0 else 'higher'} "
                                   f"(≈{abs(n):.1f} {verb} of 0.25% on average; rough — includes term premium). "
                                   f"2-year yield {y2:.2f}%."))
    if ctx.has("NFCI"):
        n = ctx.summary("NFCI")
        tight = n["latest"] > 0
        ch = n["changes"].get("13w") or 0
        sig.append(Signal("fin_conditions", "Financial conditions", -n["latest"] * 2 - ch * 4, horizon="leading",
                          group="policy", evidence=f"Chicago Fed index {n['latest']:+.2f} ({'tighter' if tight else 'looser'} "
                                                   f"than average), {'tightening' if ch > 0 else 'easing'} over 13 weeks."))
        if rr is not None and rr - NEUTRAL_REAL > 0.5 and not tight:
            notes.append("Policy looks restrictive on paper, yet financial conditions are loose — "
                         "the squeeze is not reaching markets. Transmission is weak.")
        elif rr is not None and rr - NEUTRAL_REAL < 0 and tight:
            notes.append("Policy is not tight, yet conditions are — markets are doing the tightening.")
    if ctx.has("RRPONTSYD") and ctx.has("WRESBAL") and ctx.has("GDP"):
        res = float(ctx.s("WRESBAL").iloc[-1])
        gdp = float(ctx.s("GDP").iloc[-1])
        notes.append(f"Bank reserves ${res / 1000:.2f}tn ≈ {res / gdp * 100:.1f}% of GDP. "
                     f"The Fed has signalled it wants reserves 'ample'; repo stress gauges are in Fed liquidity.")
    for sid, label in (("DFF", "Fed"), ("ECBDFR", "ECB"), ("BOE_RATE", "Bank of England"), ("IRSTCI01JPM156N", "Bank of Japan")):
        if ctx.has(sid):
            s = ctx.summary(sid)
            table.append({"bank": label, "rate": s["latest"], "obs_date": s["obs_date"], "change_12m": s["changes"].get("12m", s["changes"].get("52w")),
                          "source": s["source"], "freshness": s["freshness"]})
    if ctx.has("DFF") and ctx.has("ECBDFR"):
        gap = float(ctx.s("DFF").iloc[-1] - ctx.s("ECBDFR").iloc[-1])
        notes.append(f"US–euro policy gap {gap:+.2f}pp: a narrowing gap tends to weaken the dollar.")
    charts = [
        {"id": "cb_rates", "title": "Fed funds vs inflation", "units": "%", "start": "2000-01-01",
         "series": [{"key": "DFF", "label": "Fed funds"}, {"key": "PCEPILFE", "label": "Core PCE inflation", "transform": "yoy"},
                    {"key": "REAL_FF", "label": "Real fed funds"}], "source": "Federal Reserve; BEA (via FRED)"},
        {"id": "cb_path", "title": "What markets price for Fed policy", "units": "%", "start": "2019-01-01",
         "series": [{"key": "DFF", "label": "Fed funds"}, {"key": "DGS1", "label": "1-year yield"}, {"key": "DGS2", "label": "2-year yield"}],
         "source": "Federal Reserve H.15 (via FRED)", "note": "Yields below fed funds = cuts expected"},
        {"id": "cb_nfci", "title": "Financial conditions (above 0 = tighter than average)", "units": "index", "start": "2000-01-01",
         "series": [{"key": "NFCI", "label": "NFCI"}, {"key": "ANFCI", "label": "Adjusted NFCI"}], "source": "Chicago Fed (via FRED)"},
        {"id": "cb_global", "title": "Policy rates: Fed, ECB, BoE, BoJ", "units": "%", "start": "2015-01-01",
         "series": [{"key": "DFF", "label": "Fed"}, {"key": "ECBDFR", "label": "ECB"}, {"key": "BOE_RATE", "label": "BoE"},
                    {"key": "IRSTCI01JPM156N", "label": "BoJ (call rate)"}], "source": "Fed, ECB, BoE, OECD (via FRED/BoE)"},
    ]
    return {"signals": sig, "notes": notes, "rates_table": table, "charts": charts,
            "real_rate": rr, "neutral_assumption": NEUTRAL_REAL,
            "summaries": [ctx.summary(x) for x in ("DFF", "DFEDTARU", "IORB", "SOFR", "DTB3", "DTB6", "DGS1", "DGS2",
                                                   "DFII5", "NFCI", "ANFCI", "ECBDFR", "BOE_RATE", "IRSTCI01JPM156N",
                                                   "WRESBAL", "WSHOSHO", "QT_PACE")
                          if x in ctx.registry]}
