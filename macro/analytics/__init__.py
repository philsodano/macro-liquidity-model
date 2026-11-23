"""Run all analytics on top of the liquidity engine and build allocation inputs."""
from __future__ import annotations

from . import allocation, central_banks, consumer, cross_asset, cycle, inflation, markets
from ..transforms import ordinal
from .signals import Signal


def _clip(x, lo=-2.0, hi=2.0):
    return None if x is None else max(lo, min(hi, float(x)))


def liquidity_signals(liq: dict) -> list[Signal]:
    out = []
    for p in liq["pillars"]:
        if p["impulse"] is None:
            continue
        grp = "credit" if p["id"] == "private_credit" else "liquidity"
        out.append(Signal(f"liq_{p['id']}", p["title"], p["impulse"] + 0.5 * (p["accel"] or 0), kind="estimate",
                          horizon="leading", group=grp,
                          evidence=f"{p['title']}: {p['state']}, {p['trend']} (impulse {p['impulse']:+.2f}, "
                                   f"change over 13 weeks {(p['accel'] or 0):+.2f})."))
    c = liq["consolidated"]
    for key, label, grp in (("market", "Market liquidity (Fed, global, credit)", "liquidity"),
                            ("economy", "Economy liquidity (deficits, banks, AI capex)", "growth")):
        g = c[key]
        if g["composite"] is not None:
            out.append(Signal(f"liq_{key}", label, g["composite"] + 0.5 * (g["accel"] or 0), kind="estimate",
                              horizon="leading", group=grp,
                              evidence=f"{label}: {g['composite']:+.2f}, {g['trend']}."))
    if c["composite"] is not None:
        out.append(Signal("liq_composite", "Liquidity composite", c["composite"] + 0.5 * (c["accel"] or 0), kind="estimate",
                          horizon="leading", group="liquidity",
                          evidence=f"Composite {c['composite']:+.2f}, {c['trend']}; breadth {c['breadth']}."))
    return out


def assess_all(ctx, liq: dict) -> dict:
    infl = inflation.assess(ctx)
    cyc = cycle.assess(ctx, inflation_dir=infl["direction"])
    cb = central_banks.assess(ctx)
    con = consumer.assess(ctx)
    mk = markets.assess(ctx, recession_prob=cyc["recession_prob"])
    pill = {p["id"]: p for p in liq["pillars"]}
    r = dict(mk["readings"])
    r["liquidity_trend"] = liq["consolidated"]["accel"]
    r["global_impulse"] = pill["global"]["impulse"]
    r["leading"] = cyc["classification"]["leading"]
    xa = cross_asset.matrix(r)
    hy = ctx.summary("BAMLH0A0HYM2") if ctx.has("BAMLH0A0HYM2") else None
    factors = {
        # market liquidity is the measure that has historically lined up with risk assets (see research)
        "liquidity": _clip(liq["consolidated"]["market"]["composite"]),
        "growth": _clip(cyc["classification"]["leading"] * 1.5),
        "inflation": _clip((infl["direction"] or 0) * 2) if infl["direction"] is not None else None,
        "real_rates": _clip(-(r.get("real10_change_bp") or 0) / 25) if r.get("real10_change_bp") is not None else None,
        "credit": _clip(-(r.get("hy_change_bp") or 0) / 40) if r.get("hy_change_bp") is not None else None,
        "dollar": _clip(-(r.get("dollar_3m") or 0) / 2.5) if r.get("dollar_3m") is not None else None,
        "ai": _clip(pill["ai_capex"]["impulse"]),
    }
    comp = {c["asset"]: c for c in mk["compensation"]}
    def pv(asset, invert=False):
        p = comp.get(asset, {}).get("pctile")
        if p is None:
            return None
        v = (p - 50) / 25
        return _clip(-v if invert else v)
    hy_years = comp.get("High-yield credit", {}).get("years") or 0
    valuation = {"equities": pv("US equities"), "credit_ig": pv("Corporate credit"),
                 # ICE HY history on FRED is ~3 years — too short to call cheap/expensive; use the 20-year Baa spread
                 "credit_hy": pv("High-yield credit") if hy_years >= 10 else pv("Corporate credit"),
                 "duration": pv("Long Treasuries"),
                 "cash": _clip((r.get("real_cash") or 0) - 1) if r.get("real_cash") is not None else None}
    context = {}
    erp = comp.get("US equities", {})
    if erp.get("value") is not None:
        context["erp"] = f"Implied equity risk premium {erp['value']:.2f}% ({ordinal(erp['pctile'])} percentile since 2008)."
    cbs = {s.id: s for s in cb["signals"]}
    if "market_path" in cbs:
        context["cuts"] = cbs["market_path"].evidence
    if hy and hy["latest"] is not None:
        context["hy"] = (f"High-yield spread {hy['latest']:.2f}% ({ordinal(hy['pctile'])} percentile of only "
                         f"{hy['pctile_years']:.0f} years of data; valuation uses the 20-year Baa spread).")
        context["bdc"] = context["hy"] + " Private-credit loans are floating-rate; marks lag public markets."
    baa = comp.get("Corporate credit", {})
    if baa.get("value") is not None:
        context["ig"] = f"Baa spread {baa['value']:.2f}% ({ordinal(baa['pctile'])} percentile of {baa['years']:.0f} years)."
    if ctx.has("DFII10"):
        context["real10"] = f"10-year real yield {ctx.summary('DFII10')['latest']:.2f}%."
    if r.get("real_cash") is not None:
        context["real_cash"] = f"3-month bills pay {r['real_cash']:+.2f}% after core inflation."
    if ctx.has("DCOILWTICO"):
        context["oil"] = f"WTI oil ${ctx.summary('DCOILWTICO')['latest']:.0f}/bbl."
    if r.get("intl_us_3m") is not None:
        context["intl"] = f"Developed ex-US vs US, 3 months: {r['intl_us_3m']:+.1f}pp."
    if r.get("iwm_spy_3m") is not None:
        context["iwm"] = f"Small vs large caps, 3 months: {r['iwm_spy_3m']:+.1f}pp."
    for s in mk["sectors"]:
        if s["rel_3m"] is not None:
            context[f"sector:{s['name']}"] = f"{s['rel_3m']:+.1f}pp vs S&P 500 over 3 months."
    alloc = allocation.assess(factors, valuation, context)
    signals = liquidity_signals(liq) + cb["signals"] + con["signals"] + cyc["signals"] + infl["signals"] + mk["signals"]
    return {"central_banks": cb, "consumer": con, "cycle": cyc, "inflation": infl, "markets": mk,
            "cross_asset": xa, "allocation": alloc, "signals": signals}
