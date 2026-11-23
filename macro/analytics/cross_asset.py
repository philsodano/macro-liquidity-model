"""Cross-asset confirmation: does each market agree with the macro read? Pure function of readings."""
from __future__ import annotations


def _dir(x, th):
    if x is None:
        return None
    return 1 if x > th else -1 if x < -th else 0


TESTS = [
    # id, question, (reading_a, threshold_a, sign_a), (reading_b, threshold_b, sign_b), meanings
    ("credit_vs_liquidity", "Are credit spreads confirming the liquidity trend?",
     ("liquidity_trend", 0.25, 1), ("hy_change_bp", 15, -1),
     {"confirm": "Credit agrees with the liquidity trend.",
      "diverge": "Credit disagrees with liquidity — credit usually leads; treat the liquidity read with caution.",
      "neutral": "No clear message from one side."}),
    ("dollar_vs_global", "Is the dollar signalling tighter global conditions?",
     ("global_impulse", 0.5, 1), ("dollar_3m", 1.0, -1),
     {"confirm": "Dollar and foreign liquidity point the same way.",
      "diverge": "Dollar and foreign central banks disagree — watch EM and carry trades.",
      "neutral": "Dollar move too small to matter."}),
    ("real_yields_vs_equities", "Are real yields consistent with equity prices?",
     ("real10_change_bp", 20, -1), ("spx_3m", 3.0, 1),
     {"confirm": "Stocks are moving with the real discount rate.",
      "diverge": "Stocks and real yields disagree — if real yields rose while stocks rallied, earnings must deliver.",
      "neutral": "No strong real-yield or equity move."}),
    ("gold_vs_real_yields", "Is gold confirming monetary uncertainty?",
     ("real10_change_bp", 20, -1), ("gold_3m", 3.0, 1),
     {"confirm": "Gold moving with real yields — a normal rates story.",
      "diverge": "Gold rising despite higher real yields — buyers are hedging fiscal/monetary risk or central banks are buying.",
      "neutral": "No clear message."}),
    ("commodities_vs_growth", "Are commodities confirming stronger demand?",
     ("leading", 0.25, 1), ("copper_3m", 4.0, 1),
     {"confirm": "Copper agrees with the growth outlook.",
      "diverge": "Copper and leading indicators disagree — supply shocks or AI/grid demand may be driving metals.",
      "neutral": "No clear message."}),
    ("breadth", "Is market breadth confirming the index?",
     ("spy_3m", 3.0, 1), ("rsp_spy_3m", 2.0, 1),
     {"confirm": "Broad participation backs the index move.",
      "diverge": "Index rising on a few big stocks while the average stock lags — fragile leadership.",
      "neutral": "No clear message."}),
    ("small_caps_vs_credit", "Do small caps agree with credit?",
     ("hy_change_bp", 15, -1), ("iwm_spy_3m", 2.0, 1),
     {"confirm": "Small caps and credit agree on financing conditions.",
      "diverge": "Small caps and credit disagree — one of them is mispriced.", "neutral": "No clear message."}),
    ("vol_vs_credit", "Is equity volatility consistent with credit stress?",
     ("vix_calm", 0.5, 1), ("hy_change_bp", 40, -1),
     {"confirm": "Equity calm matches credit calm (or both are stressed).",
      "diverge": "Stock market calm while credit spreads widen — equity insurance looks cheap.", "neutral": "No clear message."}),
    ("bitcoin_vs_liquidity", "Is bitcoin tracking liquidity?",
     ("netliq_13w_pct", 1.0, 1), ("btc_3m", 10.0, 1),
     {"confirm": "Bitcoin is moving with Fed liquidity.",
      "diverge": "Bitcoin is not following liquidity — idiosyncratic flows (ETFs, treasuries) dominate.", "neutral": "No clear message."}),
]


def matrix(r: dict) -> list[dict]:
    r = dict(r)
    if r.get("vix_pctile") is not None:
        r["vix_calm"] = (50 - r["vix_pctile"]) / 25
    rows = []
    for tid, q, (a, ta, sa), (b, tb, sb), meaning in TESTS:
        da, db = _dir(r.get(a), ta), _dir(r.get(b), tb)
        obs = f"{a} = {r.get(a)}, {b} = {r.get(b)}"
        if da is None or db is None:
            v = "n/a"
            text = "Data not available."
        else:
            da, db = da * sa, db * sb
            v = "neutral" if 0 in (da, db) else "confirm" if da == db else "diverge"
            text = meaning[v]
        rows.append({"id": tid, "question": q, "observed": obs, "verdict": v, "meaning": text,
                     "a": {"key": a, "value": r.get(a)}, "b": {"key": b, "value": r.get(b)}})
    return rows
