"""Test the Druckenmiller principles against history — including where they fail.

Caveat: revised series (M2, bank credit, GDP) use today's vintages; Fed balance-sheet and market data are not
revised. The model's own vintage log removes this bias going forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..transforms import yoy
from .lags import _monthly, lead_lag


def published(s: pd.Series, months: int = 1) -> pd.Series:
    """Re-date a monthly signal to when it could have been known (one month after its observation month)."""
    s = s.dropna()
    return pd.Series(s.values, index=s.index + pd.DateOffset(months=months))


def _fwd(px: pd.Series, months: int) -> pd.Series:
    return (px.shift(-months) / px - 1) * 100


def conditional_returns(sig: pd.Series, fwd: pd.Series, th: float = 0.5) -> dict:
    df = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(df) < 24:
        return {"n": len(df), "hit_rate": None}
    active = df[df["s"].abs() > th]
    hit = float((np.sign(active["s"]) == np.sign(active["f"])).mean() * 100) if len(active) else None
    # excess version: did the signal pick above- vs below-average returns? (fair in a market that usually rises)
    ex = active["f"] - df["f"].mean()
    hit_x = float((np.sign(active["s"]) == np.sign(ex)).mean() * 100) if len(active) else None
    pos, neg, mid = df[df["s"] > th]["f"], df[df["s"] < -th]["f"], df[df["s"].abs() <= th]["f"]
    return {"n": len(df), "n_active": len(active), "hit_rate": None if hit is None else round(hit, 1),
            "hit_rate_excess": None if hit_x is None else round(hit_x, 1),
            "corr": round(float(df["s"].corr(df["f"])), 3),
            "mean_when_positive": None if pos.empty else round(float(pos.mean()), 2),
            "mean_when_negative": None if neg.empty else round(float(neg.mean()), 2),
            "mean_when_neutral": None if mid.empty else round(float(mid.mean()), 2),
            "unconditional": round(float(df["f"].mean()), 2), "start": df.index[0].strftime("%Y-%m")}


def failure_episodes(sig: pd.Series, fwd: pd.Series, th: float = 0.5, bad: float = -10, good: float = 15) -> list[dict]:
    df = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
    flags = pd.Series("", index=df.index)
    flags[(df["s"] > th) & (df["f"] < bad)] = "said supportive, stocks fell"
    flags[(df["s"] < -th) & (df["f"] > good)] = "said restrictive, stocks rallied"
    eps, cur = [], None
    for d, kind in flags.items():
        if not kind:
            continue
        if cur and cur["kind"] == kind and (d - cur["_end"]).days <= 62:
            cur["_end"] = d
            cur["months"] += 1
        else:
            cur = {"kind": kind, "_start": d, "_end": d, "months": 1}
            eps.append(cur)
    return [{"start": e["_start"].strftime("%Y-%m"), "end": e["_end"].strftime("%Y-%m"), "kind": e["kind"],
             "months": e["months"]} for e in eps]


def _verdict(hit, spread) -> str:
    if hit is None:
        return "Not testable"
    if hit >= 60 and (spread or 0) > 3:
        return "Supported"
    if hit >= 53:
        return "Partly supported"
    return "Not supported"


def _money_impulse(ctx) -> pd.Series:
    """Long-history liquidity proxy (1986+): z of 6m change in M2 growth, minus z of 6m change in Baa spread."""
    parts = []
    if ctx.has("M2SL"):
        m = _monthly(yoy(ctx.s("M2SL")), "last").diff(6)
        parts.append((m - m.rolling(120, 36).mean()) / m.rolling(120, 36).std())
    if ctx.has("BAA10Y"):
        b = _monthly(ctx.s("BAA10Y")).diff(6)
        parts.append(-(b - b.rolling(120, 36).mean()) / b.rolling(120, 36).std())
    return pd.concat(parts, axis=1).mean(axis=1).dropna() if parts else pd.Series(dtype=float)


def _recession_leads(ctx) -> list[dict]:
    if not (ctx.has("USREC") and ctx.has("BAA10Y") and ctx.has("UNRATE")):
        return []
    rec = ctx.s("USREC")
    starts = rec[(rec == 1) & (rec.shift(1) == 0)].index
    baa = _monthly(ctx.s("BAA10Y"))
    un = _monthly(ctx.s("UNRATE"), "last")
    sahm = un.rolling(3).mean() - un.rolling(12).min()
    out = []
    for st in starts[starts >= "1988-01-01"]:
        win = pd.date_range(st - pd.DateOffset(months=24), st + pd.DateOffset(months=12), freq="MS")
        b6 = baa.diff(6).reindex(win)
        credit = b6[b6 > 0.4].index
        labour = sahm.reindex(win)[sahm.reindex(win) >= 0.5].index
        out.append({"recession_start": st.strftime("%Y-%m"),
                    "credit_warning": credit[0].strftime("%Y-%m") if len(credit) else None,
                    "credit_lead_months": None if not len(credit) else int(round((st - credit[0]).days / 30.4)),
                    "labour_warning": labour[0].strftime("%Y-%m") if len(labour) else None,
                    "labour_lead_months": None if not len(labour) else int(round((st - labour[0]).days / 30.4))})
    return out


def principle_tests(ctx) -> list[dict]:
    spx = ctx.extra_series.get("SPX_LONG")
    if spx is None or spx.empty:
        return []
    f6, f12 = _fwd(spx, 6), _fwd(spx, 12)
    out = []
    allp = published(_monthly(ctx.extra_series.get("LIQ_COMPOSITE", pd.Series(dtype=float)), "last"))
    comp = published(_monthly(ctx.extra_series.get("LIQ_MARKET", pd.Series(dtype=float)), "last"))
    econ = published(_monthly(ctx.extra_series.get("LIQ_ECONOMY", pd.Series(dtype=float)), "last"))
    mi = published(_money_impulse(ctx))
    by_pillar = {}
    for p in ("central_bank", "fiscal", "banking", "private_credit", "global", "ai_capex"):
        s = ctx.extra_series.get(f"IMPULSE_{p}")
        if s is not None and not s.empty:
            r = conditional_returns(published(_monthly(s, "last")), f6)
            by_pillar[p] = {k: r.get(k) for k in ("start", "hit_rate_excess", "corr", "mean_when_positive", "mean_when_negative", "n_active")}
    # 1. Liquidity drives market direction
    r_comp = conditional_returns(comp, f6) if not comp.empty else {"hit_rate": None}
    r_all = conditional_returns(allp, f6) if not allp.empty else {"hit_rate": None}
    r_econ = conditional_returns(econ, f6) if not econ.empty else {"hit_rate": None}
    r_long = conditional_returns(mi, f6)
    spread = None if r_comp.get("mean_when_positive") is None or r_comp.get("mean_when_negative") is None else \
        r_comp["mean_when_positive"] - r_comp["mean_when_negative"]
    fails = failure_episodes(comp, f6) if not comp.empty else []
    out.append({"principle": "Liquidity drives market direction",
                "test": "When market liquidity is clearly positive (negative), are the next 6 months' stock returns above "
                        "(below) average? Signals are used one month after their observation month (publication lag). "
                        "Compared with the all-pillar and economy composites.",
                "result": r_comp, "all_pillars": r_all, "economy": r_econ, "long_history": r_long, "by_pillar": by_pillar,
                "verdict": _verdict(r_comp.get("hit_rate_excess"), spread),
                "failures": fails[:12],
                "plain": (f"Market liquidity since {r_comp.get('start')}: stocks rose {r_comp.get('mean_when_positive')}% in the "
                          f"6 months after a positive reading vs {r_comp.get('mean_when_negative')}% after a negative one; it "
                          f"picked above-average periods {r_comp.get('hit_rate_excess')}% of the time. The all-pillar average "
                          f"managed {r_all.get('hit_rate_excess')}% and the economy pillars {r_econ.get('hit_rate_excess')}% — "
                          f"liquidity works for markets only when measured the right way. Long-history money/credit proxy "
                          f"(since {r_long.get('start')}): {r_long.get('hit_rate_excess')}%.")})
    # 2. Direction & acceleration beat level
    nl = ctx.extra_series.get("NETLIQ")
    if nl is not None and not nl.empty and ctx.has("GDP"):
        m = _monthly(nl, "last")
        g = _monthly(ctx.s("GDP"), "last").resample("MS").ffill().reindex(m.index).ffill()
        level = m / g * 100
        chg = m.pct_change(3, fill_method=None) * 100
        acc = chg - chg.shift(3)
        c = {k: round(float(pd.concat([v, f6], axis=1).dropna().corr().iloc[0, 1]), 3)
             for k, v in (("level", level), ("change", chg), ("acceleration", acc))}
        best = max(c, key=lambda k: abs(c[k]))
        out.append({"principle": "Direction and acceleration matter more than level",
                    "test": "Correlation of Fed net liquidity (level vs 3m change vs change in change) with next-6m stock returns.",
                    "result": c, "verdict": "Supported" if best != "level" and abs(c[best]) > abs(c["level"]) + 0.05
                    else "Partly supported" if best != "level" else "Not supported",
                    "plain": f"Correlations with next-6m returns — level {c['level']:+.2f}, change {c['change']:+.2f}, "
                             f"acceleration {c['acceleration']:+.2f}. Strongest: {best}. All are weak in absolute terms."})
    # 3. Look 12–18 months ahead
    prof = {}
    target = _monthly(yoy(ctx.s("INDPRO")), "last") if ctx.has("INDPRO") else None
    for h in (3, 6, 12, 18):
        row = {"stocks": round(float(pd.concat([mi, _fwd(spx, h)], axis=1).dropna().corr().iloc[0, 1]), 3)}
        if target is not None:
            row["industrial_output"] = round(float(pd.concat([mi, target.shift(-h)], axis=1).dropna().corr().iloc[0, 1]), 3)
        prof[f"{h}m"] = row
    peak_g = max(prof, key=lambda k: prof[k].get("industrial_output", -9)) if target is not None else None
    peak_s = max(prof, key=lambda k: prof[k]["stocks"])
    out.append({"principle": "Look 12–18 months ahead",
                "test": "At which horizon does the long-history liquidity proxy best line up with stocks and with the economy?",
                "result": prof, "verdict": "Supported" if peak_g in ("12m", "18m") else "Partly supported",
                "plain": f"Liquidity lines up best with stocks {peak_s} ahead and with industrial output {peak_g} ahead"
                         + (" — markets react sooner than the economy." if peak_g and int(peak_s[:-1]) < int(peak_g[:-1])
                            else ". Both peak at similar horizons here; the 12–18-month lens holds for the economy.")})
    # 4. Credit exposes weakness first
    leads = _recession_leads(ctx)
    cl = [r["credit_lead_months"] for r in leads if r["credit_lead_months"] is not None]
    ll = [r["labour_lead_months"] for r in leads if r["labour_lead_months"] is not None]
    ll_lag = lead_lag(_monthly(ctx.s("BAA10Y")).diff(6), _monthly(ctx.s("UNRATE"), "last").diff(6), max_lag=18, n_boot=200,
                      expected_sign=1) if ctx.has("BAA10Y") and ctx.has("UNRATE") else {}
    out.append({"principle": "Credit exposes weakness before the economy does",
                "test": "Before each recession since 1990, did Baa spreads widen (6m change > 0.4pp) before the Sahm rule fired?",
                "result": {"episodes": leads, "baa_to_unemployment_lag": {k: ll_lag.get(k) for k in ("best_lag", "corr", "ci")}},
                "verdict": "Supported" if cl and ll and np.median(cl) > np.median(ll) else "Partly supported",
                "plain": (f"Credit spreads warned a median {np.median(cl):.0f} months before recessions began; the jobs-based "
                          f"Sahm rule fired a median {abs(np.median(ll)):.0f} month(s) {'after' if np.median(ll) < 0 else 'before'} "
                          f"they began. Widening spreads lead rising unemployment by ~{ll_lag.get('best_lag')} months."
                          if cl and ll else "Not enough episodes.")})
    # 5. Divergence creates opportunity
    if not comp.empty:
        mom = (spx / spx.shift(6) - 1) * 100
        df = pd.concat([comp.rename("liq"), mom.rename("mom"), f6.rename("f6")], axis=1).dropna()
        ignore = df[(df["liq"] < -0.5) & (df["mom"] > 5)]["f6"]  # liq = market liquidity
        wash = df[(df["liq"] > 0.5) & (df["mom"] < 0)]["f6"]
        base = float(df["f6"].mean()) if len(df) else None
        out.append({"principle": "Opportunities come when markets and liquidity disagree",
                    "test": "Next-6m returns when stocks rallied despite draining liquidity, and when they fell despite improving liquidity.",
                    "result": {"rally_into_drain": {"n": len(ignore), "mean": None if ignore.empty else round(float(ignore.mean()), 2)},
                               "selloff_into_easing": {"n": len(wash), "mean": None if wash.empty else round(float(wash.mean()), 2)},
                               "all_months": None if base is None else round(base, 2)},
                    "verdict": "Supported" if (not wash.empty and not ignore.empty and wash.mean() > base > ignore.mean())
                    else "Partly supported" if (not wash.empty and wash.mean() > (base or 0)) else "Not supported",
                    "plain": f"After sell-offs into improving liquidity, stocks returned {wash.mean():+.1f}% over 6 months "
                             f"(n={len(wash)}) vs {base:+.1f}% on average; after rallies into draining liquidity, "
                             f"{ignore.mean():+.1f}% (n={len(ignore)}). Small samples." if len(wash) and len(ignore) and base is not None
                             else "Too few divergence episodes to test."})
    # 6. Central-bank side effects
    events = []
    for sid, th, label in (("RPONTSYD", 20, "Fed repo lending spike"), ("WLCFLPCL", 20, "Discount window surge"),
                           ("SWPT", 20, "Fed swap lines tapped")):
        if ctx.has(sid):
            s = _monthly(ctx.s(sid), "last")
            hits = s[(s > th) & (s.shift(1).fillna(0) <= th)]
            for d in hits.index:
                r6 = _fwd(spx, 6).get(d)
                events.append({"date": d.strftime("%Y-%m"), "event": label, "stocks_next_6m": None if r6 is None or np.isnan(r6) else round(float(r6), 1)})
    events.sort(key=lambda e: e["date"])
    vals = [e["stocks_next_6m"] for e in events if e["stocks_next_6m"] is not None]
    out.append({"principle": "Central-bank stress and side effects create opportunities",
                "test": "Stock returns in the 6 months after the Fed's emergency facilities were first tapped.",
                "result": {"events": events}, "verdict": "Partly supported" if vals and np.median(vals) > 0 else "Not supported",
                "plain": f"{len(vals)} stress events; median next-6m stock return {np.median(vals):+.1f}%. "
                         "Buying stress worked when the Fed responded fast (2019, 2020, 2023), not in 2008." if vals else "No events."})
    return out
