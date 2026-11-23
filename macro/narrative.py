"""Plain-English text built from model outputs: executive tiles, thesis, scenarios. Every sentence is generated from
numbers in the snapshot, so the dashboard and the weekly report always say the same thing."""
from __future__ import annotations

STATE_WORD = {"adding": "adding liquidity", "draining": "draining liquidity", "neutral": "neutral", "n/a": "no data"}


def _f(x, fmt="{:.2f}", na="n/a"):
    return na if x is None else fmt.format(x)


def _tone(score: float | None, good_is_high: bool = True) -> str:
    if score is None:
        return "na"
    s = score if good_is_high else -score
    return "good" if s > 0.5 else "bad" if s < -0.5 else "neutral"


def tiles(liq: dict, a: dict, scen: dict) -> list[dict]:
    c = liq["consolidated"]
    mk, ec = c["market"], c["economy"]
    cyc, cb, con, infl, mkt = a["cycle"], a["central_banks"], a["consumer"], a["inflation"], a["markets"]
    sig = {s.id: s for s in a["signals"]}
    out = []
    cl = cyc["classification"]
    out.append({"id": "cycle", "label": "Business cycle", "value": cl["phase"].capitalize(),
                "detail": f"{'Mixed signals. ' if cl['mixed'] else ''}Recession odds (curve) {_f(cyc['recession_prob'], '{:.0f}%')}.",
                "tone": "mixed" if cl["mixed"] else _tone(cl["leading"] * 2)})
    out.append({"id": "liq_market", "label": "Market liquidity", "value": f"{mk['state'].capitalize()}, {mk['trend']}",
                "detail": f"Fed, global and credit: {_f(mk['composite'], '{:+.2f}')} (z). This is the measure that has led stocks.",
                "tone": _tone(mk["composite"])})
    out.append({"id": "liq_economy", "label": "Economy liquidity", "value": f"{ec['state'].capitalize()}, {ec['trend']}",
                "detail": f"Deficits, bank lending, AI capex: {_f(ec['composite'], '{:+.2f}')}. Feeds growth 2–4 quarters out.",
                "tone": _tone(ec["composite"])})
    rr = cb.get("real_rate")
    mp = sig.get("market_path")
    out.append({"id": "policy", "label": "Fed policy", "value": f"Real rate {_f(rr, '{:+.2f}%')}",
                "detail": (mp.evidence.split(":")[1].split("(")[0].strip().capitalize() + "." if mp else "No market path."),
                "tone": _tone(sig["real_policy_rate"].score if "real_policy_rate" in sig else None)})
    fc = sig.get("fin_conditions")
    out.append({"id": "conditions", "label": "Financial conditions", "value": "Loose" if fc and "looser" in fc.evidence else "Tight" if fc else "n/a",
                "detail": fc.evidence if fc else "", "tone": _tone(fc.score if fc else None)})
    lab = [s.score for s in con["labour_signals"]]
    out.append({"id": "consumer", "label": "Consumer & jobs", "value": con["diagnosis"].replace("-", " ").capitalize(),
                "detail": con["diagnosis_text"], "tone": "bad" if con["diagnosis"] in ("stretched",) else
                "mixed" if con["diagnosis"] in ("dissaving", "borrowing") else _tone(sum(lab) / len(lab) if lab else None)})
    core = infl["rates"].get("PCEPILFE", {})
    out.append({"id": "inflation", "label": "Inflation", "value": f"Core PCE {_f(core.get('yoy'), '{:.1f}%')}",
                "detail": f"3-month pace {_f(core.get('3m'), '{:.1f}%')}; {infl['driver']}-driven; Fed room: {infl['fed_flexibility']}.",
                "tone": _tone(sig["core_pce"].score if "core_pce" in sig else None)})
    ra = mkt["readings"].get("risk_appetite")
    out.append({"id": "appetite", "label": "Risk appetite", "value": "Risk-on" if (ra or 0) > 0.5 else "Risk-off" if (ra or 0) < -0.5 else "Neutral",
                "detail": f"VIX {_f(mkt['readings'].get('vix'), '{:.1f}')}, high-yield spreads {_f(mkt['readings'].get('hy_change_bp'), '{:+.0f}bp')} in 13 weeks.",
                "tone": _tone(ra)})
    return out


def risk_lists(a: dict) -> tuple[list[str], list[str]]:
    good, bad = [], []
    for r in a["markets"]["compensation"]:
        if r.get("value") is None:
            continue
        line = f"{r['asset']}: {r['measure'].lower()} {r.get('display', r['value'])}"
        if r["verdict"] == "well paid":
            good.append(line)
        elif r["verdict"] == "poorly paid":
            bad.append(line)
    return good, bad


def thesis(liq: dict, a: dict, scen: dict) -> list[str]:
    c = liq["consolidated"]
    cyc, infl, con = a["cycle"], a["inflation"], a["consumer"]
    core = infl["rates"].get("PCEPILFE", {})
    alloc = sorted(a["allocation"]["assets"], key=lambda x: -x["score"])
    good, bad = risk_lists(a)
    lines = [
        f"The economy is in {cyc['classification']['phase']}"
        + (" but the signals conflict." if cyc["classification"]["mixed"] else ".")
        + f" Market liquidity is {c['market']['state']} and {c['market']['trend']}; economy liquidity is "
          f"{c['economy']['state']} and {c['economy']['trend']}.",
        f"Inflation is {infl['driver']}-driven: core PCE {_f(core.get('yoy'), '{:.1f}%')} a year, "
        f"{_f(core.get('3m'), '{:.1f}%')} annualised lately — the Fed's room to ease is {infl['fed_flexibility']}.",
        f"Consumers: {con['diagnosis_text'][0].lower() + con['diagnosis_text'][1:]}",
    ]
    if bad:
        lines.append("Risk is poorly paid in " + ", ".join(b.split(":")[0] for b in bad[:3])
                     + (". Better paid: " + ", ".join(g.split(":")[0] for g in good[:3]) + "." if good else "."))
    lines.append(f"Most favoured by the framework: {alloc[0]['asset']}, {alloc[1]['asset']}. "
                 f"Least favoured: {alloc[-1]['asset']}, {alloc[-2]['asset']}.")
    return lines


def scenarios(liq: dict, a: dict, scen: dict) -> dict:
    r = a["markets"]["readings"]
    hy = next((s for s in a["markets"]["summaries"] if s["id"] == "BAMLH0A0HYM2"), {})
    hyv = hy.get("latest")
    core = a["inflation"]["rates"].get("PCEPILFE", {}).get("yoy")
    ff = next((s for s in a["central_banks"]["summaries"] if s["id"] == "DFF"), {}).get("latest")
    claims = next((s for s in a["consumer"]["labour"] if s["id"] == "ICSA"), {}).get("latest")
    c = liq["consolidated"]
    p = scen["final"]
    bull_trig = [f"High-yield spread back below {_f(hyv - 0.5 if hyv else None, '{:.1f}%')}",
                 "Dollar down 3%+ over 3 months", "Market liquidity above +0.5 and rising",
                 f"Core PCE 3-month pace under {_f((core or 3) - 0.5, '{:.1f}%')}"]
    bear_trig = [f"High-yield spread above {_f(hyv + 1.5 if hyv else None, '{:.1f}%')}",
                 f"Jobless claims 4-week average above {_f(claims * 1.2 if claims else None, '{:.0f}k')}",
                 "Sahm indicator at 0.3 or higher", "Market liquidity below −0.5 and falling"]
    return {
        "base": {"name": "Base: slow grind", "probability": p["base"],
                 "economy": f"Growth near trend; the cycle reads '{a['cycle']['label']}'.",
                 "liquidity": f"Market liquidity stays {c['market']['state']}; deficits keep adding to incomes.",
                 "central_bank": f"Fed near {_f(ff, '{:.2f}%')}; inflation ({_f(core, '{:.1f}%')}) keeps cuts slow.",
                 "consumer": a["consumer"]["diagnosis_text"],
                 "markets": "Returns come from income more than multiple expansion; dispersion stays high.",
                 "confirm": ["Claims stay low", "Credit spreads stable", "Core inflation drifts down slowly"],
                 "invalidate": bull_trig[:2] + bear_trig[:2]},
        "bull": {"name": "Bull: liquidity turns up", "probability": p["bull"],
                 "economy": "AI investment and productivity lift growth while inflation cools.",
                 "liquidity": "Dollar weakens, credit spreads tighten, foreign central banks ease.",
                 "central_bank": "Fed cuts because inflation lets it, not because growth breaks.",
                 "consumer": "Real wages rise; spending is funded by income, not borrowing.",
                 "markets": "Equities and credit outperform; small caps and cyclicals lead; breadth widens.",
                 "confirm": bull_trig, "invalidate": bear_trig[:2]},
        "bear": {"name": "Bear: credit cracks, Fed boxed in", "probability": p["bear"],
                 "economy": "Leading indicators roll over and unemployment rises.",
                 "liquidity": "Credit spreads widen, the dollar rallies, market liquidity drains.",
                 "central_bank": "Inflation stops the Fed from easing early; it cuts late.",
                 "consumer": "Lower-income stress spreads: delinquencies rise, saving is already low.",
                 "markets": f"Equities de-rate from a thin risk premium; Treasuries and cash outperform.",
                 "confirm": bear_trig, "invalidate": bull_trig[:2]},
    }
