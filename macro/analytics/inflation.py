"""F. Inflation: trend, breadth, demand- vs supply-driven, expectations, and what it means for the Fed."""
from __future__ import annotations

import pandas as pd

from ..transforms import ann_rate, yoy
from .signals import Signal, missing

TARGET = 2.0


def _rates(s: pd.Series) -> dict:
    s = s.dropna()
    if len(s) < 13:
        return {}
    y, a3, a6 = yoy(s).dropna(), ann_rate(s, 3).dropna(), ann_rate(s, 6).dropna()
    if y.empty or a3.empty or a6.empty:
        return {}
    return {"yoy": float(y.iloc[-1]), "3m": float(a3.iloc[-1]), "6m": float(a6.iloc[-1]),
            "yoy_date": y.index[-1].strftime("%Y-%m"), "3m_date": a3.index[-1].strftime("%Y-%m")}


def direction(rates: dict) -> float | None:
    """Average of (3-month annualised − 12-month) for core PCE and core CPI: > 0 = core inflation speeding up.
    Using both keeps the read current when one release (PCE) lags the other (CPI)."""
    d = [r["3m"] - r["yoy"] for k, r in rates.items() if k in ("PCEPILFE", "CPILFESL") and r]
    return sum(d) / len(d) if d else None


def decompose(supercore_3m, wages_yoy, core_goods_3m, energy_yoy, import_yoy) -> tuple[str, str]:
    demand_hot = (supercore_3m or 0) > 3.0 or (wages_yoy or 0) > 4.0
    supply_hot = (core_goods_3m or 0) > 1.5 or (energy_yoy or 0) > 10 or (import_yoy or 0) > 3
    if demand_hot and supply_hot:
        return "broad", "Both demand (services, wages) and supply (goods, energy, imports) are pushing prices up."
    if demand_hot:
        return "demand", "Mostly demand: services and wages run hot while goods and energy are calm."
    if supply_hot:
        return "supply", "Mostly supply: goods, energy or import prices (tariffs, dollar, oil) are driving it."
    return "cooling", "Neither demand nor supply pressures are hot."


def assess(ctx) -> dict:
    r = {k: _rates(ctx.s(k)) for k in ("CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "CUSR0000SAH1", "IA001260M",
                                       "CUSR0000SACL1E", "CUSR0000SASLE", "PPIFIS", "IR") if ctx.has(k)}
    sig, notes = [], []
    core = r.get("PCEPILFE", {})
    if core:
        trend = core["3m"] - core["yoy"]
        sig.append(Signal("core_pce", "Core PCE inflation (Fed target)", (2.8 - core["3m"]) * 1.2 - trend * 0.5,
                          horizon="lagging", group="inflation",
                          evidence=f"Core PCE {core['yoy']:.1f}% y/y, {core['3m']:.1f}% annualised over 3 months "
                                   f"({'speeding up' if trend > 0.2 else 'slowing' if trend < -0.2 else 'steady'}). Target 2%."))
    else:
        sig.append(missing("core_pce", "Core PCE", "inflation", "no core PCE"))
    cc = r.get("CPILFESL", {})
    if cc:
        tr = cc["3m"] - cc["yoy"]
        sig.append(Signal("core_cpi", "Core CPI (first inflation report each month)", (3.1 - cc["3m"]) * 1.2 - tr * 0.5,
                          horizon="lagging", group="inflation",
                          evidence=f"Core CPI {cc['3m']:.1f}% annualised over 3 months, {cc['yoy']:.1f}% over 12 months "
                                   f"(12-month figure to {cc['yoy_date']})."))
    wages = ctx.summary("FRBATLWGT3MMAUMHWGO")["latest"] if ctx.has("FRBATLWGT3MMAUMHWGO") else None
    energy = ctx.summary("DCOILWTICO")["yoy"] if ctx.has("DCOILWTICO") else None
    kind, text = decompose(r.get("IA001260M", {}).get("3m"), wages, r.get("CUSR0000SACL1E", {}).get("3m"), energy,
                           r.get("IR", {}).get("yoy"))
    notes.append(text)
    exp = {}
    for sid in ("T5YIE", "T5YIFR", "MICH", "EXPINF1YR"):
        if ctx.has(sid):
            exp[sid] = ctx.summary(sid)
    if "T5YIFR" in exp:
        v = exp["T5YIFR"]["latest"]
        anchored = 1.9 <= v <= 2.6
        sig.append(Signal("expectations", "Long-run inflation expectations", 1 if anchored else -1.2, horizon="leading",
                          group="inflation", evidence=f"5y5y forward {v:.2f}% — {'anchored' if anchored else 'drifting'}."))
    flex = "n/a"
    if core:
        gap = core["3m"] - TARGET
        flex = "high" if gap < 0.5 else "limited" if gap < 1.25 else "low"
        notes.append({"high": "Inflation near target: the Fed has room to ease if growth weakens.",
                      "limited": "Inflation above target: the Fed has little room to ease and may tighten further.",
                      "low": "Inflation well above target: the Fed is under pressure to tighten even if growth slows."}[flex])
        if r.get("PCEPILFE") and ctx.has("DFF"):
            notes.append("If inflation falls while the Fed holds, the real rate rises — passive tightening.")
    if ctx.has("ULCNFB") and ctx.has("OPHNFB"):
        u, p = ctx.summary("ULCNFB"), ctx.summary("OPHNFB")
        if u["yoy"] is not None and p["yoy"] is not None:
            notes.append(f"Productivity {p['yoy']:+.1f}% y/y and unit labour costs {u['yoy']:+.1f}% y/y "
                         f"({p['period']}): {'productivity is absorbing wage growth' if u['yoy'] < 2.5 else 'wage costs are outpacing productivity'}.")
    table = []
    labels = {"CPIAUCSL": "CPI", "CPILFESL": "Core CPI", "PCEPI": "PCE", "PCEPILFE": "Core PCE", "CUSR0000SAH1": "Shelter",
              "IA001260M": "Services ex housing & energy", "CUSR0000SACL1E": "Core goods", "CUSR0000SASLE": "Services ex energy",
              "PPIFIS": "Producer prices", "IR": "Import prices"}
    for k, v in r.items():
        s = ctx.summary(k)
        table.append({"id": k, "label": labels[k], "yoy": round(v["yoy"], 2), "3m": round(v["3m"], 2), "6m": round(v["6m"], 2),
                      "yoy_date": v["yoy_date"],
                      "obs_date": s["obs_date"], "freshness": s["freshness"], "source": s["source"]})
    charts = [
        {"id": "in_core", "title": "Core inflation: 12-month vs 3-month pace", "units": "%", "start": "2015-01-01",
         "series": [{"key": "PCEPILFE", "label": "Core PCE, y/y", "transform": "yoy"},
                    {"key": "PCEPILFE", "label": "Core PCE, 3m annualised", "transform": "ann3"},
                    {"key": "CPILFESL", "label": "Core CPI, y/y", "transform": "yoy"}], "source": "BEA; BLS (via FRED)"},
        {"id": "in_parts", "title": "Where inflation comes from", "units": "% y/y", "start": "2015-01-01",
         "series": [{"key": "CUSR0000SAH1", "label": "Shelter", "transform": "yoy"},
                    {"key": "IA001260M", "label": "Services ex housing & energy", "transform": "yoy"},
                    {"key": "CUSR0000SACL1E", "label": "Core goods", "transform": "yoy"}], "source": "BLS; BEA (via FRED)"},
        {"id": "in_exp", "title": "Inflation expectations", "units": "%", "start": "2010-01-01",
         "series": [{"key": "T5YIE", "label": "5-year breakeven"}, {"key": "T5YIFR", "label": "5y5y forward"},
                    ], "source": "Federal Reserve (via FRED)"},
    ]
    direction_ = direction(r)
    return {"rates": r, "table": table, "driver": kind, "notes": notes, "fed_flexibility": flex,
            "expectations": [exp[k] for k in exp], "signals": sig, "charts": charts, "direction": direction_,
            "summaries": [ctx.summary(x) for x in ("DCOILWTICO", "GASREGW", "DHHNGSP", "PCOPPUSDM", "PALLFNFINDEXM",
                                                   "CES0500000003", "FRBATLWGT3MMAUMHWGO", "ECIWAG", "ULCNFB", "OPHNFB",
                                                   "CORESTICKM159SFRBATL", "MEDCPIM158SFRBCLE", "PCETRIM12M159SFRBDAL")
                          if ctx.has(x)]}
