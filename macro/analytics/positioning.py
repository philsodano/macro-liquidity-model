"""Positioning & leverage: how exposed hedge funds, dealers and leveraged investors are — in plain words.

Horizons differ: Form PF (quarterly, ~5 months old) is a slow backdrop; CFTC futures and margin debt move over
weeks to months; options-market gauges move over days. Every item says which.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..transforms import ordinal, percentile, yoy
from .signals import Signal

SLOW = "Backdrop (6–18 months) · quarterly data, about 5 months old"
MEDIUM = "Weeks to months"
FAST = "Days to weeks"


def ls_ratio(long: float | None, short: float | None) -> float | None:
    if long is None or not short:
        return None
    return long / short


def net_exposure(long: float | None, short: float | None) -> float | None:
    if long is None or short is None or (long + short) == 0:
        return None
    return (long - short) / (long + short) * 100


def _pz(p: float | None) -> float | None:
    """Percentile (0–100) → rough z-like score (−2..+2)."""
    return None if p is None else max(-2.0, min(2.0, (p - 50) / 25))


def _yoy_z(s: pd.Series, years: int = 10) -> float | None:
    """z-score of the latest year-on-year % change against the last `years` of y/y changes."""
    y = yoy(s).dropna()
    w = y[y.index >= y.index[-1] - pd.DateOffset(years=years)] if len(y) else y
    return None if len(w) < 12 or not w.std() else float((w.iloc[-1] - w.mean()) / w.std())


def _derive(ctx) -> None:
    s = ctx.s
    if ctx.has("HF_EQ_LONG") and ctx.has("HF_EQ_SHORT"):
        df = pd.concat([s("HF_EQ_LONG").rename("L"), s("HF_EQ_SHORT").rename("S")], axis=1).dropna()
        ctx.put("HF_LS_RATIO", (df["L"] / df["S"].replace(0, np.nan)).dropna())
        ctx.put("HF_NET_EXPOSURE", ((df["L"] - df["S"]) / (df["L"] + df["S"]).replace(0, np.nan) * 100).dropna())
    if ctx.has("HF_GAV") and ctx.has("HF_NAV"):
        ctx.put("HF_LEVERAGE", (s("HF_GAV") / s("HF_NAV").replace(0, np.nan)).dropna())
    if ctx.has("VIXCLS") and ctx.has("VXVCLS"):
        ctx.put("VIX_TERM", (s("VIXCLS") / s("VXVCLS").replace(0, np.nan)).dropna())
    if ctx.has("MARGIN_DEBT") and ctx.has("MARGIN_FREE_MARGIN") and ctx.has("MARGIN_FREE_CASH"):
        df = pd.concat([s("MARGIN_DEBT"), s("MARGIN_FREE_MARGIN"), s("MARGIN_FREE_CASH")], axis=1).dropna()
        ctx.put("MARGIN_NET", df.iloc[:, 0] - df.iloc[:, 1] - df.iloc[:, 2])


def _item(ctx, sid: str, label: str, horizon: str, plain_fn, years: int = 20) -> dict:
    if sid not in ctx.registry or not ctx.has(sid):
        return {"id": sid, "label": label, "value": None, "horizon": horizon, "plain": "No data yet.", "freshness": "missing",
                "source": ctx.registry[sid].source if sid in ctx.registry else "", "units": ctx.registry[sid].units if sid in ctx.registry else ""}
    summ = ctx.summary(sid)
    ser = ctx.s(sid)
    ser = ser[ser.index >= ser.index[-1] - pd.DateOffset(years=years)]
    pct = percentile(ser, years)
    yrs = round((ser.index[-1] - ser.index[0]).days / 365.25, 1)
    out = {"id": sid, "label": label, "value": summ["latest"], "units": summ["units"], "period": summ["period"],
           "obs_date": summ["obs_date"], "freshness": summ["freshness"], "source": summ["source"], "pctile": pct,
           "years": yrs, "yoy": summ["yoy"], "horizon": horizon}
    out["plain"] = plain_fn(out)
    return out


def _crowd_word(p: float | None) -> str:
    if p is None:
        return ""
    return "crowded long" if p >= 80 else "unusually short — fuel for a squeeze" if p <= 20 else "not extreme"


def _side(v: float) -> str:
    return "long" if v >= 0 else "short"


def assess(ctx) -> dict:
    _derive(ctx)
    pf_age = " Form PF data, about 5 months old."
    hedge = [
        _item(ctx, "HF_NET_EXPOSURE", "Net stock exposure", SLOW,
              lambda i: f"Hedge funds are {i['value']:.0f}% net long stocks ({i['period']}; {ordinal(i['pctile'])} percentile of "
                        f"{i['years']:.0f} years): " + ("crowded — little left to buy." if i["pctile"] >= 80 else
                                                        "defensive — room to add risk later." if i["pctile"] <= 20 else "normal.")
                        + pf_age),
        _item(ctx, "HF_LS_RATIO", "Long/short ratio", SLOW,
              lambda i: f"${i['value']:.2f} of stock longs for every $1 of shorts ({i['period']})." + pf_age),
        _item(ctx, "HF_LEVERAGE", "Leverage", SLOW,
              lambda i: f"Gross assets are {i['value']:.1f}x investors' money ({i['period']}; {ordinal(i['pctile'])} percentile). "
                        "More leverage = more forced selling in a shock." + pf_age),
        _item(ctx, "HF_REPO_BORROW", "Repo borrowing", SLOW,
              lambda i: f"${i['value']:,.0f}bn borrowed overnight against bonds ({i['period']}"
                        + (f", {i['yoy']:+.0f}% in a year" if i.get("yoy") is not None else "") + "). This funding can vanish in stress."
                        + pf_age),
        _item(ctx, "HF_PB_BORROW", "Prime-broker borrowing", SLOW,
              lambda i: f"${i['value']:,.0f}bn borrowed from banks' prime brokers ({i['period']}"
                        + (f", {i['yoy']:+.0f}% in a year" if i.get("yoy") is not None else "") + ")." + pf_age),
    ]
    fut_plain = lambda name: (lambda i: f"Hedge funds are net {_side(i['value'])} {abs(i['value']):.0f}% of {name} futures "  # noqa: E731
                                        f"({ordinal(i['pctile'])} percentile of {i['years']:.0f} years): {_crowd_word(i['pctile'])}.")
    futures = [
        _item(ctx, "CFTC_ES_LEV_NET", "Hedge funds: S&P 500", MEDIUM, fut_plain("S&P 500"), years=10),
        _item(ctx, "CFTC_ES_LEV_LS", "Hedge funds: S&P 500 long/short ratio", MEDIUM,
              lambda i: f"{i['value']:.2f} long contracts per short ({ordinal(i['pctile'])} percentile). Futures shorts are often "
                        "hedges, so watch the trend.", years=10),
        _item(ctx, "CFTC_NQ_LEV_NET", "Hedge funds: Nasdaq-100", MEDIUM, fut_plain("Nasdaq-100"), years=10),
        _item(ctx, "CFTC_RTY_LEV_NET", "Hedge funds: small caps", MEDIUM, fut_plain("Russell 2000"), years=10),
        _item(ctx, "CFTC_ES_AM_NET", "Pension & mutual funds: S&P 500", MEDIUM,
              lambda i: f"Asset managers are net {_side(i['value'])} {abs(i['value']):.0f}% of S&P futures "
                        f"({ordinal(i['pctile'])} percentile): " + ("fully invested." if i["pctile"] >= 80 else "room to add." if i["pctile"] <= 30 else "normal."),
              years=10),
        _item(ctx, "CFTC_DX_LEV_NET", "Hedge funds: US dollar", MEDIUM, fut_plain("US dollar index"), years=10),
    ]
    basis_plain = lambda i: (f"Hedge funds are net short Treasury futures worth ${abs(i['value']):,.0f}mn per 0.01% yield move "  # noqa: E731
                             f"({ordinal(100 - i['pctile'])} percentile for size): the 'basis trade' — short futures, own bonds with "
                             "borrowed money. The bigger it is, the bigger the forced selling if funding dries up.")
    leverage = [
        _item(ctx, "MARGIN_DEBT", "Margin debt", MEDIUM,
              lambda i: f"${i['value']:,.0f}bn borrowed to buy stocks ({i['period']}"
                        + (f", {i['yoy']:+.0f}% in a year" if i.get("yoy") is not None else "") + "). Fast growth = leveraged buying."),
        _item(ctx, "MARGIN_NET", "Margin debt minus idle cash", MEDIUM,
              lambda i: f"${i['value']:,.0f}bn after subtracting cash in brokerage accounts ({i['period']}; "
                        f"{ordinal(i['pctile'])} percentile of {i['years']:.0f} years)."),
        _item(ctx, "HF_TREAS_BASIS", "Treasury basis trade", MEDIUM, basis_plain, years=10),
    ]
    banks = [
        _item(ctx, "PD_TREAS_NET", "Dealer Treasury holdings", MEDIUM,
              lambda i: f"Big banks' dealer desks hold ${i['value']:,.0f}bn of Treasuries ({ordinal(i['pctile'])} percentile of "
                        f"{i['years']:.0f} years). " + ("High: balance sheets are filling up — less room to absorb selling."
                                                       if i["pctile"] >= 80 else "Room to absorb more supply.")),
        _item(ctx, "TASACBW027SBOG", "Banks' government bonds", MEDIUM,
              lambda i: f"Banks hold ${i['value']:,.0f}bn of Treasury and agency bonds"
                        + (f" ({i['yoy']:+.1f}% in a year)" if i.get("yoy") is not None else "") + " — exposed to rising yields."),
        _item(ctx, "LNFACBW027SBOG", "Bank loans to nonbank lenders", MEDIUM,
              lambda i: f"${i['value']:,.0f}bn lent by banks to funds, BDCs and finance companies"
                        + (f" ({i['yoy']:+.0f}% in a year)" if i.get("yoy") is not None else "") + " — banks' indirect exposure to private credit."),
    ]
    if ctx.has("KRE") and ctx.has("SPY"):
        k, s_ = ctx.s("KRE"), ctx.s("SPY")
        def r13(x):
            p = x[x.index <= x.index[-1] - pd.Timedelta(weeks=13)]
            return float(x.iloc[-1] / p.iloc[-1] - 1) * 100 if len(p) else None
        rel = None if r13(k) is None or r13(s_) is None else r13(k) - r13(s_)
        if rel is not None:
            banks.append({"id": "KRE_REL", "label": "Regional bank stocks vs market", "value": round(rel, 1), "units": "pp, 3 months",
                          "horizon": MEDIUM, "freshness": ctx.summary("KRE")["freshness"], "source": "tiingo",
                          "obs_date": ctx.summary("KRE")["obs_date"], "period": ctx.summary("KRE")["period"],
                          "plain": f"Regional banks {rel:+.1f}pp vs the S&P 500 over 3 months — "
                                   + ("investors are worried about bank losses." if rel < -5 else "no sign of bank stress." if rel > -2 else "mild underperformance.")})
    vrp = None
    if ctx.has("VIXCLS") and ctx.has("SP500"):
        r = np.log(ctx.s("SP500")).diff().dropna()
        vrp = float(ctx.s("VIXCLS").iloc[-1] - r.tail(21).std() * math.sqrt(252) * 100)
    options = [
        _item(ctx, "VIX_TERM", "VIX curve", FAST,
              lambda i: f"1-month ÷ 3-month VIX = {i['value']:.2f}. "
                        + ("Inverted (above 1): investors pay up for protection right now — acute stress."
                           if i["value"] > 1 else "Flat: hedging demand is rising." if i["value"] > 0.95
                           else "Normal upward slope: no panic."), years=10),
        _item(ctx, "CFTC_VIX_LEV_NET", "Hedge funds: VIX futures", FAST,
              lambda i: f"Hedge funds are net {_side(i['value'])} {abs(i['value']):.0f}% of VIX futures. "
                        + ("Big short = many selling volatility insurance; a shock forces them to buy it back."
                           if i["value"] < 0 else "Net long volatility: already hedged."), years=10),
    ]
    options.append({"id": "VRP", "label": "Implied vs actual volatility", "value": None if vrp is None else round(vrp, 1),
                    "units": "VIX points", "horizon": FAST, "freshness": ctx.summary("VIXCLS")["freshness"] if ctx.has("VIXCLS") else "missing",
                    "source": "fred", "obs_date": ctx.summary("VIXCLS")["obs_date"] if ctx.has("VIXCLS") else None,
                    "period": ctx.summary("VIXCLS")["period"] if ctx.has("VIXCLS") else None,
                    "plain": "No data yet." if vrp is None else
                    f"Options price {vrp:+.1f} points more volatility than stocks have actually shown (last month). "
                    + ("Protection is expensive — fear is high." if vrp > 8 else "Protection is cheap — complacency." if vrp < 0 else "Normal premium.")})

    # ---- three simple signals (score > 0 = supportive for risk assets) ----
    def val(items, sid):
        return next((i for i in items if i["id"] == sid and i.get("value") is not None), None)

    sigs = []
    es, hfn, md = val(futures, "CFTC_ES_LEV_NET"), val(hedge, "HF_NET_EXPOSURE"), val(leverage, "MARGIN_DEBT")
    comps = [x for x in (_pz(es["pctile"]) if es else None, _pz(hfn["pctile"]) if hfn else None,
                         _yoy_z(ctx.s("MARGIN_DEBT")) if md else None) if x is not None]
    if comps:
        c = float(np.mean(comps))
        word = "crowded long" if c > 0.75 else "light (room to buy)" if c < -0.75 else "normal"
        sigs.append(Signal("crowding", "Crowding", -c, kind="estimate", horizon="leading", group="positioning",
                           evidence=f"Positioning is {word}. " + " ".join(
                               x for x in (f"S&P futures {es['pctile']:.0f}th pct." if es else "",
                                           f"Hedge fund net exposure {hfn['value']:.0f}% ({hfn['period']})." if hfn else "",
                                           f"Margin debt {md['yoy']:+.0f}% y/y." if md and md.get("yoy") is not None else "") if x)))
    else:
        sigs.append(Signal("crowding", "Crowding", 0, "No data yet.", group="positioning", available=False))
    basis, mnet = val(leverage, "HF_TREAS_BASIS"), val(leverage, "MARGIN_NET")
    comps = [x for x in (_pz(100 - basis["pctile"]) if basis else None,
                         _yoy_z(ctx.s("MARGIN_NET")) if mnet else None) if x is not None]
    if comps:
        f = float(np.mean(comps))
        word = "high" if f > 0.75 else "low" if f < -0.75 else "moderate"
        bits = [f"basis trade {ordinal(100 - basis['pctile'])} percentile for size" if basis else "",
                f"margin debt net of cash {ordinal(mnet['pctile'])} percentile" + (f", {mnet['yoy']:+.0f}% y/y" if mnet.get("yoy") is not None else "")
                if mnet else ""]
        sigs.append(Signal("fragility", "Leverage & fragility", -f, kind="estimate", horizon="leading", group="positioning",
                           evidence=f"Forced-selling risk is {word}: " + "; ".join(b for b in bits if b) + "."))
    else:
        sigs.append(Signal("fragility", "Leverage & fragility", 0, "No data yet.", group="positioning", available=False))
    vt = val(options, "VIX_TERM")
    if vt:
        v = vt["value"]
        vixp = percentile(ctx.s("VIXCLS"), 20) if ctx.has("VIXCLS") else 50
        score, word = ((-1.2, "acute stress (VIX curve inverted)") if v > 1 else (-0.4, "rising hedging demand") if v > 0.95
                       else (-0.5, "complacent (cheap protection)") if v < 0.85 and vixp < 30 else (0.0, "calm"))
        sigs.append(Signal("hedging", "Options market", score, kind="estimate", horizon="coincident", group="positioning",
                           evidence=f"Options market: {word}. VIX curve {v:.2f}" + (f"; implied minus actual volatility {vrp:+.1f}." if vrp is not None else ".")))
    else:
        sigs.append(Signal("hedging", "Options market", 0, "No data yet.", group="positioning", available=False))

    charts = [
        {"id": "pos_futures", "title": "Hedge funds' net stock futures", "units": "% of open interest", "start": "2012-01-01",
         "series": [{"key": "CFTC_ES_LEV_NET", "label": "S&P 500"}, {"key": "CFTC_NQ_LEV_NET", "label": "Nasdaq-100"},
                    {"key": "CFTC_RTY_LEV_NET", "label": "Russell 2000"}],
         "source": "CFTC Traders in Financial Futures (leveraged funds), weekly", "note": "Above 0 = net long"},
        {"id": "pos_hf", "title": "Hedge funds' net stock exposure", "units": "% of gross exposure", "start": "2013-01-01",
         "series": [{"key": "HF_NET_EXPOSURE", "label": "Net exposure"}],
         "source": "SEC Form PF via OFR Hedge Fund Monitor (quarterly, ~5 months lag)"},
        {"id": "pos_basis", "title": "Treasury basis trade (hedge funds' net Treasury futures)", "units": "USD mn per 0.01% yield move",
         "start": "2012-01-01", "series": [{"key": "HF_TREAS_BASIS", "label": "Net position"}],
         "source": "CFTC via OFR Hedge Fund Monitor, weekly", "note": "More negative = bigger leveraged short"},
        {"id": "pos_margin", "title": "Margin debt, growth vs a year ago", "units": "% y/y", "start": "1998-01-01",
         "series": [{"key": "MARGIN_DEBT", "label": "Margin debt", "transform": "yoy"}], "source": "FINRA margin statistics, monthly",
         "recessions": True},
        {"id": "pos_vix", "title": "VIX curve (1-month ÷ 3-month)", "units": "ratio", "start": "2015-01-01",
         "series": [{"key": "VIX_TERM", "label": "VIX ÷ VIX3M"}], "source": "Cboe via FRED", "note": "Above 1 = inverted (stress)"},
    ]
    live = [s for s in sigs if s.available]
    summary = (" ".join(s.evidence.split(".")[0] + "." for s in live) if live else "No positioning data yet.")
    return {"hedge_funds": hedge, "futures": futures, "leverage": leverage, "banks": banks, "options": options,
            "signals": sigs, "charts": charts, "summary": summary,
            "horizons": {"slow": SLOW, "medium": MEDIUM, "fast": FAST},
            "note": "No options greeks (dealer gamma) — that needs a paid or registered options feed; possible future upgrade."}
