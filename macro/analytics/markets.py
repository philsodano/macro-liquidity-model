"""G. Markets & risk compensation: is risk being paid for? Produces the readings used for cross-asset tests."""
from __future__ import annotations

from ..transforms import ordinal

import math

import numpy as np
import pandas as pd

from ..transforms import percentile, yoy
from .signals import Signal, missing

SECTORS = {"XLK": "Technology", "XLC": "Communication services", "XLY": "Consumer discretionary", "XLP": "Consumer staples",
           "XLV": "Health care", "XLF": "Financials", "KRE": "Regional banks", "XLI": "Industrials", "XLE": "Energy",
           "XLB": "Materials", "XLU": "Utilities", "XLRE": "Real estate", "XHB": "Homebuilders", "SMH": "Semiconductors",
           "IGV": "Software"}


def ret(s: pd.Series, weeks: int) -> float | None:
    s = s.dropna()
    if s.empty:
        return None
    prior = s[s.index <= s.index[-1] - pd.Timedelta(weeks=weeks)]
    return None if prior.empty else float((s.iloc[-1] / prior.iloc[-1] - 1) * 100)


def rel(a: pd.Series, b: pd.Series, weeks: int) -> float | None:
    ra, rb = ret(a, weeks), ret(b, weeks)
    return None if ra is None or rb is None else ra - rb


def chg_bp(s: pd.Series, weeks: int = 13) -> float | None:
    s = s.dropna()
    if s.empty:
        return None
    prior = s[s.index <= s.index[-1] - pd.Timedelta(weeks=weeks)]
    return None if prior.empty else float((s.iloc[-1] - prior.iloc[-1]) * 100)


def verdict_from_pctile(p: float | None, higher_is_better_paid: bool = True) -> str:
    if p is None:
        return "n/a"
    q = p if higher_is_better_paid else 100 - p
    return "well paid" if q >= 60 else "poorly paid" if q <= 25 else "fairly paid"


def assess(ctx, recession_prob: float | None = None) -> dict:
    g = ctx.s
    R: dict[str, float | None] = {}
    eq = g("SPY") if ctx.has("SPY") else g("SP500")
    R["spx_3m"] = ret(eq, 13)
    R["spx_12m"] = ret(eq, 52)
    R["spy_3m"] = ret(g("SPY"), 13) if ctx.has("SPY") else None
    R["rsp_spy_3m"] = rel(g("RSP"), g("SPY"), 13) if ctx.has("RSP") and ctx.has("SPY") else None
    R["iwm_spy_3m"] = rel(g("IWM"), g("SPY"), 13) if ctx.has("IWM") and ctx.has("SPY") else None
    R["growth_value_3m"] = rel(g("IVW"), g("IVE"), 13) if ctx.has("IVW") and ctx.has("IVE") else None
    R["intl_us_3m"] = rel(g("EFA"), g("SPY"), 13) if ctx.has("EFA") and ctx.has("SPY") else None
    R["gold_3m"] = ret(g("GLD"), 13) if ctx.has("GLD") else None
    R["copper_3m"] = ret(g("CPER"), 13) if ctx.has("CPER") else ret(g("PCOPPUSDM"), 13) if ctx.has("PCOPPUSDM") else None
    R["oil_3m"] = ret(g("DCOILWTICO"), 13) if ctx.has("DCOILWTICO") else None
    R["btc_3m"] = ret(g("CBBTCUSD"), 13) if ctx.has("CBBTCUSD") else None
    R["dollar_3m"] = ret(g("DTWEXBGS"), 13) if ctx.has("DTWEXBGS") else None
    R["real10_change_bp"] = chg_bp(g("DFII10")) if ctx.has("DFII10") else None
    R["ten_change_bp"] = chg_bp(g("DGS10")) if ctx.has("DGS10") else None
    R["hy_change_bp"] = chg_bp(g("BAMLH0A0HYM2")) if ctx.has("BAMLH0A0HYM2") else None
    R["curve_change_bp"] = chg_bp((g("DGS10") - g("DGS2")).dropna()) if ctx.has("DGS10") and ctx.has("DGS2") else None
    R["vix"] = float(g("VIXCLS").iloc[-1]) if ctx.has("VIXCLS") else None
    R["vix_pctile"] = percentile(g("VIXCLS")) if ctx.has("VIXCLS") else None
    R["netliq_13w_pct"] = None
    if "NETLIQ" in ctx.extra_series:
        R["netliq_13w_pct"] = ret(ctx.extra_series["NETLIQ"], 13)
    # realised vol and volatility risk premium
    if ctx.has("SP500"):
        r = np.log(g("SP500")).diff().dropna()
        rv = float(r.tail(21).std() * math.sqrt(252) * 100)
        R["realised_vol"] = rv
        if R["vix"] is not None:
            R["vrp"] = R["vix"] - rv
        dd = g("SP500")
        dd = dd[dd.index >= dd.index[-1] - pd.Timedelta(days=365)]
        R["spx_drawdown"] = float((dd.iloc[-1] / dd.max() - 1) * 100)
    # curve shape
    shape = "n/a"
    if R["curve_change_bp"] is not None and R["ten_change_bp"] is not None:
        steep = R["curve_change_bp"] > 10
        flat = R["curve_change_bp"] < -10
        up = R["ten_change_bp"] > 0
        shape = ("bear steepening" if up else "bull steepening") if steep else \
                ("bear flattening" if up else "bull flattening") if flat else "little change"
    # risk compensation table
    comp = []
    def row(asset, sid, label, higher_better=True, fmt="{:.2f}%"):
        if not ctx.has(sid):
            comp.append({"asset": asset, "measure": label, "value": None, "pctile": None, "years": None,
                         "verdict": "n/a", "source": ctx.registry[sid].source if sid in ctx.registry else ""})
            return None
        s = ctx.summary(sid)
        comp.append({"asset": asset, "measure": label, "value": s["latest"], "display": fmt.format(s["latest"]),
                     "pctile": s["pctile"], "years": s["pctile_years"], "obs_date": s["obs_date"],
                     "verdict": verdict_from_pctile(s["pctile"], higher_better), "source": s["source"]})
        return s
    erp = row("US equities", "ERP_DAMODARAN", "Implied equity risk premium")
    row("Corporate credit", "BAA10Y", "Baa spread over Treasuries")
    hy = row("High-yield credit", "BAMLH0A0HYM2", "High-yield spread (3y history only)")
    tp = row("Long Treasuries", "ACMTP10", "10-year term premium")
    row("Real yields", "DFII10", "10-year real yield")
    if ctx.has("DTB3") and ctx.has("PCEPILFE"):
        real_cash = float(g("DTB3").iloc[-1] - yoy(g("PCEPILFE")).dropna().iloc[-1])
        R["real_cash"] = real_cash
        comp.append({"asset": "Cash", "measure": "3-month bill minus core inflation", "value": round(real_cash, 2),
                     "display": f"{real_cash:+.2f}%", "pctile": None, "years": None,
                     "verdict": "well paid" if real_cash > 1.5 else "poorly paid" if real_cash < 0 else "fairly paid",
                     "source": "fred", "kind": "estimate"})
    if R.get("vrp") is not None:
        comp.append({"asset": "Volatility", "measure": "VIX minus realised volatility", "value": round(R["vrp"], 1),
                     "display": f"{R['vrp']:+.1f} pts", "pctile": None, "years": None,
                     "verdict": "insurance cheap" if R["vix_pctile"] and R["vix_pctile"] < 30 else "insurance pricey"
                     if R["vix_pctile"] and R["vix_pctile"] > 70 else "normal", "source": "fred", "kind": "estimate"})
    sig = []
    if erp:
        sig.append(Signal("equity_valuation", "Equity risk premium", (erp["pctile"] - 50) / 25, kind="estimate",
                          horizon="lagging", group="valuation",
                          evidence=f"Implied ERP {erp['latest']:.2f}% — {ordinal(erp['pctile'])} percentile since 2008. "
                                   f"{'Thin cushion for bad news.' if erp['pctile'] < 30 else 'Reasonable cushion.'}"))
    else:
        sig.append(missing("equity_valuation", "Equity risk premium", "valuation", "Damodaran file unavailable"))
    baa = ctx.summary("BAA10Y") if ctx.has("BAA10Y") else None
    if baa:
        sig.append(Signal("credit_valuation", "Credit spreads vs history", (baa["pctile"] - 50) / 25, horizon="leading",
                          group="valuation", evidence=f"Baa spread {baa['latest']:.2f}% — {ordinal(baa['pctile'])} percentile of "
                                                      f"{baa['pctile_years']:.0f} years. Tight spreads pay little for default risk."))
    if R["hy_change_bp"] is not None:
        sig.append(Signal("credit_momentum", "Credit spread trend", -R["hy_change_bp"] / 40, horizon="leading", group="credit",
                          evidence=f"High-yield spreads {R['hy_change_bp']:+.0f}bp over 13 weeks."))
    appetite = []
    if R["vix_pctile"] is not None:
        appetite.append((50 - R["vix_pctile"]) / 25)
    if R["hy_change_bp"] is not None:
        appetite.append(-R["hy_change_bp"] / 50)
    if R["spx_3m"] is not None:
        appetite.append(R["spx_3m"] / 5)
    if R["btc_3m"] is not None:
        appetite.append(R["btc_3m"] / 25)
    ra = float(np.clip(np.mean(appetite), -2, 2)) if appetite else None
    R["risk_appetite"] = ra
    if ra is not None:
        sig.append(Signal("risk_appetite", "Risk appetite", ra, horizon="coincident", group="valuation", kind="estimate",
                          evidence="Blend of VIX level, credit-spread trend, 3-month stock return and bitcoin."))
    sectors = []
    if ctx.has("SPY"):
        for t, name in SECTORS.items():
            if ctx.has(t):
                sectors.append({"ticker": t, "name": name, "rel_3m": rel(g(t), g("SPY"), 13), "rel_12m": rel(g(t), g("SPY"), 52),
                                "ret_3m": ret(g(t), 13)})
        sectors.sort(key=lambda r: -(r["rel_3m"] or -99))
    charts = [
        {"id": "mk_curve", "title": "Treasury yields", "units": "%", "start": "2000-01-01",
         "series": [{"key": "DGS3MO", "label": "3-month"}, {"key": "DGS2", "label": "2-year"}, {"key": "DGS10", "label": "10-year"},
                    {"key": "DGS30", "label": "30-year"}], "source": "Federal Reserve H.15 (via FRED)"},
        {"id": "mk_real_tp", "title": "Real yield and term premium (10-year)", "units": "%", "start": "2004-01-01",
         "series": [{"key": "DFII10", "label": "Real yield (TIPS)"}, {"key": "ACMTP10", "label": "Term premium (ACM)"}],
         "source": "Federal Reserve; NY Fed ACM model"},
        {"id": "mk_erp", "title": "Equity risk premium (implied)", "units": "%", "start": "2008-01-01",
         "series": [{"key": "ERP_DAMODARAN", "label": "Implied ERP"}], "source": "Damodaran (NYU Stern), monthly"},
        {"id": "mk_vix", "title": "Volatility (VIX)", "units": "index", "start": "2007-01-01",
         "series": [{"key": "VIXCLS", "label": "VIX"}], "source": "Cboe (via FRED)"},
        {"id": "mk_other", "title": "Dollar, oil and bitcoin (rebased to 100)", "units": "index, start = 100", "start": "2021-01-01",
         "series": [{"key": "DTWEXBGS", "label": "Dollar", "transform": "rebase"}, {"key": "DCOILWTICO", "label": "Oil (WTI)", "transform": "rebase"},
                    {"key": "CBBTCUSD", "label": "Bitcoin", "transform": "rebase"}, {"key": "GLD", "label": "Gold", "transform": "rebase"}],
         "source": "Federal Reserve; EIA; Coinbase (via FRED); Tiingo"},
    ]
    return {"readings": {k: (None if v is None else round(v, 2)) for k, v in R.items()}, "curve_shape": shape,
            "compensation": comp, "signals": sig, "sectors": sectors, "charts": charts,
            "summaries": [ctx.summary(x) for x in ("DGS3MO", "DGS2", "DGS10", "DGS30", "DFII10", "T10YIE", "ACMTP10",
                                                   "BAMLH0A0HYM2", "BAMLC0A0CM", "BAA10Y", "SP500", "NASDAQCOM",
                                                   "VIXCLS", "ERP_DAMODARAN", "DTWEXBGS", "DCOILWTICO", "CBBTCUSD",
                                                   "PCOPPUSDM", "GLD", "SPY", "IWM", "RSP") if x in ctx.registry]}
