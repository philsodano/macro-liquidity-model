"""Pillar 3 — Banks: credit creation, deposits, lending standards, loans to nonbank lenders."""
from __future__ import annotations

import pandas as pd

from .common import build_pillar

CATEGORIES = {"TOTCI": "Business (C&I)", "CREACBW027SBOG": "Commercial real estate", "CLSACBW027SBOG": "Consumer",
              "CCLACBW027SBOG": "Credit cards", "LNFACBW027SBOG": "Nonbank lenders (private credit etc.)"}


def credit_impulse(credit: pd.Series, ngdp: pd.Series, weeks: int = 52) -> pd.Series:
    """Change in the 12-month flow of credit, as pp of nominal GDP."""
    c = credit.dropna()
    flow = c.diff(weeks)
    g = ngdp.dropna()
    gm = g.reindex(g.index.union(c.index)).ffill().reindex(c.index)
    return ((flow - flow.shift(weeks)) / gm * 100).dropna()


def ann_growth_13w(s: pd.Series) -> float | None:
    s = s.dropna()
    if len(s) < 14:
        return None
    return ((s.iloc[-1] / s.iloc[-14]) ** 4 - 1) * 100


def assess(ctx) -> dict:
    drivers, growth = [], {}
    if ctx.has("TOTBKCR") and ctx.has("GDP"):
        ci = ctx.put("BANK_CREDIT_IMPULSE", credit_impulse(ctx.s("TOTBKCR"), ctx.s("GDP")))
        if len(ci):
            drivers.append(f"Bank credit impulse {ci.iloc[-1]:+.2f}pp of GDP (change in the yearly credit flow).")
    for sid, label in CATEGORIES.items():
        if ctx.has(sid):
            g = ann_growth_13w(ctx.s(sid))
            if g is not None:
                growth[label] = round(g, 1)
    if growth:
        top = sorted(growth.items(), key=lambda kv: -kv[1])
        drivers.append("Loan growth, last 13 weeks annualised: " + " · ".join(f"{k} {v:+.1f}%" for k, v in top))
    if ctx.has("DRTSCILM"):
        s = ctx.summary("DRTSCILM")
        word = "tightening" if s["latest"] > 0 else "easing"
        drivers.append(f"Net {abs(s['latest']):.0f}% of banks {word} business-loan standards ({s['period']}).")
    charts = [
        {"id": "bank_growth", "explain": "Growth over the past year in bank credit (all lending and securities), bank loans, and the money supply (M2). Banks create new money when they lend, so faster growth means more money flowing into the economy. Deposits and M2 are shown for context, not added on top.", "title": "Bank credit and loans, growth vs a year ago", "units": "% y/y", "start": "2000-01-01",
         "series": [{"key": "TOTBKCR", "label": "Bank credit", "transform": "yoy"},
                    {"key": "TOTLL", "label": "Loans", "transform": "yoy"},
                    {"key": "M2SL", "label": "M2 money", "transform": "yoy"}],
         "source": "Federal Reserve H.8 and H.6 (via FRED)"},
        {"id": "bank_sloos", "explain": "Share of banks tightening their lending rules, from the Fed's survey of loan officers. Above zero = more banks tightening than easing. Tighter rules today usually mean slower loan growth and more defaults 6–12 months later.", "title": "Banks tightening lending standards", "units": "net % of banks", "start": "1995-01-01",
         "series": [{"key": "DRTSCILM", "label": "Business loans"}, {"key": "DRTSCLCC", "label": "Credit cards"}],
         "source": "Federal Reserve Senior Loan Officer Survey (via FRED)", "note": "Above 0 = more banks tightening"},
        {"id": "bank_ndfi", "explain": "Loans from banks to non-bank lenders — private credit funds, business development companies, finance companies. This is how bank money feeds private credit. Fast growth shows banks' indirect exposure to private credit is rising.", "title": "Bank loans to nonbank lenders", "units": "USD bn", "start": "2015-01-01",
         "series": [{"key": "LNFACBW027SBOG", "label": "Loans to nondepository financials"}],
         "source": "Federal Reserve H.8 (via FRED)", "note": "Bank money funding private credit, BDCs, finance companies"},
    ]
    return build_pillar(
        ctx, "banking", "Bank lending", ["TOTBKCR"],
        ["TOTBKCR", "TOTLL", "TOTCI", "CREACBW027SBOG", "CLSACBW027SBOG", "CCLACBW027SBOG", "LNFACBW027SBOG",
         "DPSACBW027SBOG", "M2SL", "DRTSCILM", "DRSDCILM", "DRTSCLCC", "BANK_CREDIT_IMPULSE"],
        blurb="Banks create new money when they lend. This is the main private source of new liquidity.",
        drivers=drivers or ["Not enough data."],
        transmission="Looser standards → more loans → new deposits → spending and investment. "
                     "Standards lead loan growth by 2–4 quarters.",
        classification="Creation. Bank lending creates deposits. Deposits and M2 are shown but not added "
                       "(they are the other side of the same loans). Bank loans to private-credit funds count here only.",
        timing="Standards: leading (2–4 quarters). Loan volumes: coincident to lagging.",
        charts=charts, extra={"loan_growth_13w": growth})
