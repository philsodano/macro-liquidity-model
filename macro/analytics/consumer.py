"""D. Consumer & labour: is demand real (income) or borrowed (credit, dissaving)? Who is stretched?"""
from __future__ import annotations

import pandas as pd

from .signals import Signal, missing


def _yoy(ctx, sid):
    return ctx.summary(sid)["yoy"] if ctx.has(sid) else None


def funding_diagnosis(real_pce_yoy, real_dpi_yoy, saving_chg_12m, credit_yoy, nominal_income_yoy) -> tuple[str, str]:
    if real_pce_yoy is None or real_dpi_yoy is None:
        return "n/a", "Not enough data."
    dissaving = real_pce_yoy > real_dpi_yoy + 0.5 and (saving_chg_12m or 0) < -0.3
    borrowing = credit_yoy is not None and nominal_income_yoy is not None and credit_yoy > nominal_income_yoy + 1
    if dissaving and borrowing:
        return "stretched", "Spending is outrunning income, financed by lower saving and more borrowing."
    if dissaving:
        return "dissaving", "Spending is outrunning real income; households are saving less to keep spending."
    if borrowing:
        return "borrowing", "Credit is growing faster than income; borrowing is supporting spending."
    return "income-funded", "Spending is in line with income growth — the healthiest kind."


def assess(ctx) -> dict:
    lab, con = [], []
    if ctx.has("PAYEMS"):
        p = ctx.s("PAYEMS").dropna()
        avg3 = float(p.diff().tail(3).mean())
        ctx.put("PAYROLL_3M_AVG", p.diff().rolling(3).mean())
        lab.append(Signal("payrolls", "Job growth (3-month average)", (avg3 - 75) / 75, horizon="coincident", group="labour",
                          evidence=f"Payrolls {avg3:+.0f}k a month over the last 3 months."))
    if ctx.has("ICSA"):
        c = ctx.s("ICSA").dropna()
        ma4 = c.rolling(4).mean()
        rise = float(ma4.iloc[-1] / ma4.tail(26).min() * 100 - 100)
        lab.append(Signal("claims", "New jobless claims", (12 - rise) / 8, horizon="leading", group="labour",
                          evidence=f"4-week average {ma4.iloc[-1]:.0f}k, {rise:.0f}% above its 6-month low "
                                   "(a 20%+ rise has preceded past downturns)."))
    if ctx.has("UNRATE"):
        u = ctx.summary("UNRATE")
        ch = u["changes"].get("12m") or 0
        lab.append(Signal("unemployment", "Unemployment rate", -ch * 2, horizon="lagging", group="labour",
                          evidence=f"Unemployment {u['latest']:.1f}%, {ch:+.1f}pp over 12 months."))
    if ctx.has("JTSQUL"):
        q = ctx.summary("JTSQUL")
        lab.append(Signal("quits", "People quitting jobs", (q["pct_changes"].get("12m") or 0) / 10, horizon="leading",
                          group="labour", evidence=f"Quits {q['pct_changes'].get('12m') or 0:+.1f}% y/y — workers' confidence."))
    real_wage = None
    if ctx.has("CES0500000003") and ctx.has("CPIAUCSL"):
        real_wage = _yoy(ctx, "CES0500000003") - _yoy(ctx, "CPIAUCSL")
        lab.append(Signal("real_wages", "Real wage growth", real_wage, horizon="lagging", group="consumer",
                          evidence=f"Wages {_yoy(ctx, 'CES0500000003'):+.1f}% y/y vs prices {_yoy(ctx, 'CPIAUCSL'):+.1f}% → "
                                   f"real {real_wage:+.1f}%."))
    rpce, rdpi = _yoy(ctx, "PCEC96"), _yoy(ctx, "DSPIC96")
    sav = ctx.summary("PSAVERT") if ctx.has("PSAVERT") else None
    sav12 = sav["changes"].get("12m") if sav else None
    credit = _yoy(ctx, "TOTALSL")
    inc_nom = None
    if ctx.has("DSPIC96") and ctx.has("PCEPI"):
        inc_nom = (rdpi or 0) + (_yoy(ctx, "PCEPI") or 0)
    diag, diag_text = funding_diagnosis(rpce, rdpi, sav12, credit, inc_nom)
    if rpce is not None:
        con.append(Signal("real_spending", "Real consumer spending", (rpce - 1.5) / 1.0, horizon="coincident",
                          group="consumer", evidence=f"Real spending {rpce:+.1f}% y/y; nominal {(_yoy(ctx, 'PCE') or 0):+.1f}% "
                                                     f"— the gap is inflation."))
    if rdpi is not None:
        con.append(Signal("real_income", "Real disposable income", (rdpi - 1.0) / 1.0, horizon="coincident",
                          group="consumer", evidence=f"Real after-tax income {rdpi:+.1f}% y/y."))
    if sav:
        con.append(Signal("saving", "Saving rate", (sav["latest"] - 4.5) / 1.5, horizon="lagging", group="consumer",
                          evidence=f"Saving rate {sav['latest']:.1f}% ({(sav12 or 0):+.1f}pp in 12 months). Low saving = less cushion."))
    stress = []
    for sid, label in (("DRCCLACBS", "Credit card"), ("DROCLACBS", "Auto & other consumer loan")):
        if ctx.has(sid):
            s = ctx.summary(sid)
            ch = s["changes"].get("12m") or 0
            stress.append(f"{label} delinquency {s['latest']:.2f}% ({ch:+.2f}pp y/y, {s['period']}).")
            con.append(Signal(f"delinq_{sid}", f"{label} delinquencies", -ch * 3 - (s["pctile"] - 50) / 40,
                              horizon="coincident", group="consumer", evidence=stress[-1]))
    if ctx.has("DRTSCLCC"):
        s = ctx.summary("DRTSCLCC")
        stress.append(f"Net {s['latest']:.0f}% of banks tightening credit cards ({s['period']}).")
    k_shape = ("Lower-income households: watch card and auto delinquencies, card tightening and real wages. "
               "Higher-income households: supported by asset prices (wealth effect) and interest income. "
               "No free monthly data on spending by income group — this split uses proxies.")
    implications = []
    if diag in ("stretched", "dissaving", "borrowing"):
        implications.append("Consumer-facing earnings rely on spending that income does not fully cover — "
                            "vulnerable if credit tightens or jobs weaken. Discretionary and low-end retail most exposed.")
    else:
        implications.append("Income-backed spending supports revenue for consumer companies; margins depend on wage costs.")
    if any("delinquency" in s and "+" in s.split("(")[1][:2] for s in stress):
        implications.append("Rising delinquencies point to lender losses (cards, autos, BNPL) before they hit spending.")
    charts = [
        {"id": "co_jobs", "title": "Jobs and jobless claims", "units": "thousands", "start": "2015-01-01",
         "series": [{"key": "PAYROLL_3M_AVG", "label": "Payroll growth, 3m avg (k/month)"},
                    {"key": "ICSA", "label": "Initial claims (k/week)", "axis": 1}], "source": "BLS; Dept of Labor (via FRED)"},
        {"id": "co_unemp", "title": "Unemployment and the Sahm rule", "units": "%", "start": "2000-01-01",
         "series": [{"key": "UNRATE", "label": "Unemployment rate"}, {"key": "SAHMREALTIME", "label": "Sahm indicator (pp)"}],
         "source": "BLS (via FRED)", "recessions": True},
        {"id": "co_income", "title": "Real income vs real spending", "units": "% y/y", "start": "2015-01-01",
         "series": [{"key": "DSPIC96", "label": "Real disposable income", "transform": "yoy"},
                    {"key": "PCEC96", "label": "Real spending", "transform": "yoy"}], "source": "BEA (via FRED)"},
        {"id": "co_stress", "title": "Household stress: delinquency rates", "units": "%", "start": "2000-01-01",
         "series": [{"key": "DRCCLACBS", "label": "Credit cards"}, {"key": "DROCLACBS", "label": "Other consumer (mostly auto)"}],
         "source": "Federal Reserve (via FRED)", "recessions": True},
    ]
    labour_ids = ["PAYEMS", "UNRATE", "SAHMREALTIME", "ICSA", "CCSA", "JTSJOL", "JTSHIL", "JTSQUL", "CES0500000003",
                  "FRBATLWGT3MMAUMHWGO", "CIVPART", "LNS11300060", "TEMPHELPS", "AWHAETP", "U6RATE", "ECIWAG"]
    consumer_ids = ["DSPIC96", "PCE", "PCEC96", "RSAFS", "RRSFS", "PSAVERT", "TOTALSL", "REVOLSL", "CCLACBW027SBOG",
                    "DRCCLACBS", "DROCLACBS", "TDSP", "UMCSENT", "DRTSCLCC"]
    return {"labour_signals": lab, "consumer_signals": con, "signals": lab + con, "diagnosis": diag,
            "diagnosis_text": diag_text, "stress": stress, "k_shape": k_shape, "implications": implications,
            "real_wage": real_wage, "charts": charts,
            "labour": [ctx.summary(x) for x in labour_ids if ctx.has(x)],
            "consumer": [ctx.summary(x) for x in consumer_ids if ctx.has(x)]}
