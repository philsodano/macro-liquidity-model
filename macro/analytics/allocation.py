"""H. Allocation framework: transparent factor scores, not buy/sell calls.

Factors (each −2..+2, + = tailwind direction):
  liquidity  + = liquidity improving          growth  + = growth strengthening ahead
  inflation  + = inflation rising             real_rates + = real yields falling
  credit     + = credit conditions easing      dollar  + = dollar weakening
  ai         + = AI capex accelerating
Sensitivities are judgement-based hypotheses, documented here and testable against history.
"""
from __future__ import annotations

LABELS = {"liquidity": ("liquidity improving", "liquidity draining"), "growth": ("growth strengthening", "growth slowing"),
          "inflation": ("inflation rising", "inflation falling"), "real_rates": ("real yields falling", "real yields rising"),
          "credit": ("credit easing", "credit tightening"), "dollar": ("dollar weakening", "dollar strengthening"),
          "ai": ("AI capex accelerating", "AI capex slowing")}
INVALIDATE = {"liquidity": "Liquidity composite turns to draining for 2+ months.",
              "growth": "Leading indicators roll over or jobless claims rise 20%+ from their low.",
              "inflation": "Core inflation trend reverses.", "real_rates": "10-year real yield moves 50bp against the position.",
              "credit": "High-yield spreads widen 100bp+.", "dollar": "Dollar moves 5%+ the other way.",
              "ai": "Hyperscalers cut capex guidance or funding strain shows in their bond spreads."}
CONFIRM = {"liquidity": "Net liquidity and bank credit keep rising.", "growth": "Permits, orders and payrolls firm.",
           "inflation": "Breakevens and core inflation move as expected.", "real_rates": "Real yields keep trending the right way.",
           "credit": "Spreads stay tight with new issuance open.", "dollar": "Dollar trend persists.",
           "ai": "Capex, construction and chip output keep growing."}

ASSETS = {
    "US equities": ({"liquidity": .5, "growth": .6, "inflation": -.2, "real_rates": .4, "credit": .4}, "equities", "erp"),
    "International equities": ({"liquidity": .4, "growth": .4, "real_rates": .2, "credit": .2, "dollar": .6}, "equities", "intl"),
    "Small caps": ({"liquidity": .5, "growth": .8, "inflation": -.2, "real_rates": .5, "credit": .7}, "equities", "iwm"),
    "Growth stocks": ({"liquidity": .6, "growth": .2, "inflation": -.4, "real_rates": .8, "credit": .2, "ai": .5}, "equities", "erp"),
    "Value stocks": ({"liquidity": .3, "growth": .6, "inflation": .3, "real_rates": -.1, "credit": .4}, "equities", "erp"),
    "Government bonds": ({"liquidity": .2, "growth": -.7, "inflation": -.8, "real_rates": 1.0, "credit": -.3}, "duration", "cuts"),
    "Investment-grade credit": ({"liquidity": .3, "growth": .2, "inflation": -.4, "real_rates": .6, "credit": .6}, "credit_ig", "ig"),
    "High-yield credit": ({"liquidity": .5, "growth": .6, "inflation": -.2, "real_rates": .2, "credit": .9}, "credit_hy", "hy"),
    "Private credit": ({"liquidity": .5, "growth": .5, "inflation": .1, "real_rates": -.1, "credit": .9}, "credit_private", "bdc"),
    "Cash": ({"liquidity": -.4, "growth": -.3, "real_rates": -.6, "credit": -.4}, "cash", "real_cash"),
    "Gold": ({"liquidity": .4, "growth": -.1, "inflation": .5, "real_rates": .8, "credit": -.2, "dollar": .7}, "gold", "real10"),
    "Commodities": ({"liquidity": .3, "growth": .7, "inflation": .8, "real_rates": .1, "dollar": .5, "ai": .2}, "commodities", "oil"),
    "Real assets": ({"liquidity": .4, "growth": .3, "inflation": .3, "real_rates": .7, "credit": .4, "ai": .2}, "real_assets", "real10"),
}
SECTORS = {
    "Technology": {"liquidity": .5, "growth": .3, "real_rates": .6, "ai": .9},
    "Semiconductors": {"liquidity": .5, "growth": .5, "real_rates": .4, "ai": 1.0},
    "Software": {"liquidity": .5, "growth": .3, "real_rates": .7, "ai": .3},
    "Communication services": {"liquidity": .4, "growth": .3, "real_rates": .5, "ai": .6},
    "Consumer discretionary": {"liquidity": .4, "growth": .8, "inflation": -.3, "real_rates": .4, "credit": .5},
    "Consumer staples": {"growth": -.4, "inflation": -.2, "real_rates": .3},
    "Health care": {"growth": -.3, "real_rates": .2},
    "Financials": {"liquidity": .3, "growth": .6, "real_rates": -.3, "credit": .6},
    "Regional banks": {"liquidity": .5, "growth": .5, "real_rates": .2, "credit": .9},
    "Industrials": {"liquidity": .3, "growth": .8, "credit": .3, "ai": .5},
    "Energy": {"growth": .5, "inflation": .9, "dollar": .3},
    "Materials": {"growth": .7, "inflation": .5, "dollar": .5},
    "Utilities": {"growth": -.3, "real_rates": .7, "ai": .6},
    "Real estate": {"liquidity": .4, "growth": .3, "real_rates": .9, "credit": .5},
    "Homebuilders": {"liquidity": .4, "growth": .4, "real_rates": .9, "credit": .4},
}
VAL_WEIGHT = 0.35


def stance(score: float) -> str:
    return ("Attractive" if score >= 1 else "Mildly attractive" if score >= .4 else "Neutral" if score > -.4
            else "Mildly unattractive" if score > -1 else "Unattractive")


def _score(sens: dict, factors: dict, val: float | None):
    contrib, denom = [], 0.0
    for f, s in sens.items():
        x = factors.get(f)
        denom += abs(s)
        if x is not None:
            contrib.append({"factor": f, "contribution": round(s * x, 3), "label": LABELS[f][0 if x >= 0 else 1]})
    macro = sum(c["contribution"] for c in contrib) / denom if denom else 0.0
    total = macro if val is None else (1 - VAL_WEIGHT) * macro + VAL_WEIGHT * val
    if val is not None:
        contrib.append({"factor": "valuation", "contribution": round(VAL_WEIGHT * val, 3),
                        "label": "cheap vs history" if val > 0 else "expensive vs history"})
    contrib.sort(key=lambda c: -abs(c["contribution"]))
    return max(-2.0, min(2.0, total)), contrib


def _describe(name: str, score: float, contrib: list[dict], priced: str | None, sens: dict) -> dict:
    pos = [c for c in contrib if c["contribution"] > 0.02]
    neg = [c for c in contrib if c["contribution"] < -0.02]
    why = []
    if pos:
        why.append("Helped by " + ", ".join(c["label"] for c in pos[:2]) + ".")
    if neg:
        why.append("Hurt by " + ", ".join(c["label"] for c in neg[:2]) + ".")
    key = (pos or neg or [{"factor": max(sens, key=lambda k: abs(sens[k]))}])[0]["factor"]
    key = key if key in INVALIDATE else max(sens, key=lambda k: abs(sens[k]))
    return {"score": round(score, 2), "stance": stance(score),
            "thesis": f"{stance(score)}: the macro mix {'favours' if score > 0.4 else 'works against' if score < -0.4 else 'is balanced for'} {name.lower()}.",
            "why": " ".join(why) or "No strong macro force either way.",
            "priced_in": priced or "No market-implied expectation available.",
            "invalidation": INVALIDATE[key], "confirmation": CONFIRM[key], "contributions": contrib}


def assess(factors: dict, valuation: dict, context: dict) -> dict:
    assets = []
    for name, (sens, vkey, pkey) in ASSETS.items():
        sc, contrib = _score(sens, factors, valuation.get(vkey))
        assets.append({"asset": name, **_describe(name, sc, contrib, context.get(pkey), sens)})
    sectors = []
    for name, sens in SECTORS.items():
        sc, contrib = _score(sens, factors, None)
        sectors.append({"asset": name, **_describe(name, sc, contrib, context.get(f"sector:{name}"), sens)})
    sectors.sort(key=lambda a: -a["score"])
    return {"assets": assets, "sectors": sectors, "factors": factors, "valuation": valuation,
            "method": "Score = weighted macro factors (65%) + valuation (35%), each −2 to +2. Sensitivities are "
                      "judgement-based and listed in macro/analytics/allocation.py. Not buy/sell recommendations."}
