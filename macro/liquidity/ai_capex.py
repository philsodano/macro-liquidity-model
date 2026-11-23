"""Pillar 6 — AI capex: how much hyperscalers spend, and who funds it."""
from __future__ import annotations

import pandas as pd

from .common import build_pillar, fmt_bn, fmt_level

FIRMS = ["MSFT", "GOOGL", "AMZN", "META", "ORCL"]


def to_calendar_quarter(s: pd.Series) -> pd.Series:
    """Map fiscal quarter ends (e.g. Oracle's Aug 31) to the calendar quarter holding most of their months."""
    s = s.dropna()
    q = (s.index - pd.Timedelta(days=15)).to_period("Q").to_timestamp(how="end").normalize()
    return pd.Series(s.values, index=q).groupby(level=0).sum()


def firm_table(ctx) -> pd.DataFrame:
    rows = []
    for f in FIRMS:
        for kind in ("CAPEX", "OCF", "DEBT_ISS", "LEASE"):
            sid = f"{kind}_{f}"
            if sid in ctx.registry and ctx.has(sid):
                s = to_calendar_quarter(ctx.s(sid))
                rows.append(pd.DataFrame({"firm": f, "kind": kind, "q": s.index, "v": s.values}))
    if not rows:
        return pd.DataFrame(columns=["firm", "kind", "q", "v"])
    return pd.concat(rows, ignore_index=True)


def ai_funding_split(t: pd.DataFrame) -> pd.DataFrame:
    """Per calendar quarter, summed over firms that reported capex that quarter."""
    if t.empty:
        return pd.DataFrame()
    piv = t.pivot_table(index=["q", "firm"], columns="kind", values="v", aggfunc="sum")
    piv = piv[piv.get("CAPEX").notna()] if "CAPEX" in piv else piv.iloc[0:0]
    g = piv.groupby(level=0)
    out = pd.DataFrame({
        "firms": g.size(),
        "capex": g["CAPEX"].sum(),
        "ocf": g["OCF"].sum() if "OCF" in piv else 0.0,
        "debt_issued": g["DEBT_ISS"].sum() if "DEBT_ISS" in piv else 0.0,
        "lease_principal": g["LEASE"].sum() if "LEASE" in piv else 0.0,
    })
    out["fcf_after_capex"] = out["ocf"] - out["capex"]
    out["internal_share"] = (out[["ocf", "capex"]].min(axis=1) / out["capex"] * 100).clip(0, 100)
    out["external_share"] = 100 - out["internal_share"]
    out["capex_to_ocf"] = out["capex"] / out["ocf"] * 100
    return out


def assess(ctx) -> dict:
    t = firm_table(ctx)
    split = ai_funding_split(t)
    drivers, extra = [], {}
    if not split.empty:
        full = split[split["firms"] == len(FIRMS)]
        if not full.empty:
            ctx.put("AI_CAPEX_TOTAL", full["capex"])
            ctx.put("AI_CAPEX_TO_OCF", full["capex_to_ocf"])
            last = full.iloc[-1]
            q = full.index[-1]
            yoy = full["capex"].pct_change(4).iloc[-1] * 100 if len(full) > 4 else None
            drivers.append(f"Big Tech capex {fmt_level(last['capex'])} in {q.year}Q{q.quarter}"
                           + (f", {yoy:+.0f}% y/y." if yoy is not None else "."))
            drivers.append(f"Capex is {last['capex_to_ocf']:.0f}% of their operating cash flow; "
                           f"{last['internal_share']:.0f}% funded internally.")
            last4 = full.tail(4)
            debt4 = float(last4["debt_issued"].sum())
            drivers.append(f"Debt raised over the last 4 quarters: {fmt_level(debt4)} "
                           f"(vs capex {fmt_level(float(last4['capex'].sum()))}).")
            extra["funding_last4q"] = {"capex": round(float(last4["capex"].sum()), 1),
                                       "ocf": round(float(last4["ocf"].sum()), 1), "debt_issued": round(debt4, 1),
                                       "lease_principal": round(float(last4["lease_principal"].sum()), 1)}
            per_firm = t[(t["kind"] == "CAPEX")].sort_values("q").groupby("firm").tail(4).groupby("firm")["v"].sum()
            extra["capex_by_firm_4q"] = {k: round(float(v), 1) for k, v in per_firm.sort_values(ascending=False).items()}
            extra["split"] = split.reset_index().assign(q=lambda d: d["q"].dt.strftime("%Y-%m-%d")).round(2).to_dict("records")
    for sid, label in (("PROFCONS", "Office/data-center construction"), ("PRPWRCONS", "Power construction")):
        if ctx.has(sid):
            s = ctx.summary(sid)
            if s["yoy"] is not None:
                drivers.append(f"{label} {s['yoy']:+.1f}% y/y ({s['period']}).")
    drivers.append("Not captured: off-balance-sheet structures (e.g. joint-venture data centers funded by private "
                   "credit, operating leases not yet started). These move debt off hyperscaler balance sheets.")
    charts = [
        {"id": "ai_capex", "title": "Big Tech capex vs operating cash flow", "units": "USD bn per quarter", "start": "2015-01-01",
         "series": [{"key": "AI_CAPEX_TOTAL", "label": "Capex (5 firms)"}, {"key": "AI_OCF_TOTAL", "label": "Operating cash flow"}],
         "source": "SEC 10-Q/10-K XBRL (MSFT, GOOGL, AMZN, META, ORCL)", "kind": "bar"},
        {"id": "ai_build", "title": "Physical buildout", "units": "USD bn, annual rate", "start": "2015-01-01",
         "series": [{"key": "PROFCONS", "label": "Office + data centers"}, {"key": "PRPWRCONS", "label": "Power"},
                    {"key": "PRMFGCONS", "label": "Factories (incl. chip fabs)"}],
         "source": "Census construction spending (via FRED)"},
    ]
    if not split.empty:
        full = split[split["firms"] == len(FIRMS)]
        ctx.put("AI_OCF_TOTAL", full["ocf"])
    return build_pillar(
        ctx, "ai_capex", "AI investment", ["AI_CAPEX_TOTAL"],
        ["AI_CAPEX_TOTAL", "PROFCONS", "PRPWRCONS", "PRMFGCONS", "Y033RC1Q027SBEA", "A34SNO", "IPG3344S", "SMH"],
        blurb="Where AI spending comes from and where the money goes.",
        drivers=drivers,
        transmission="Capex flows to chipmakers, equipment, construction, utilities and power. It lifts GDP "
                     "and earnings in those industries; it does not add much new money to the system.",
        classification="Mostly redistribution: funded from cash flow (existing corporate cash). Bond issuance "
                       "moves investors' savings to hyperscalers. New credit is created only where banks lend "
                       "(counted under Bank lending). Leases and joint ventures move risk off balance sheets.",
        timing="Coincident for GDP and industrial demand; earnings of suppliers lead the capex itself.",
        charts=charts, extra=extra)
