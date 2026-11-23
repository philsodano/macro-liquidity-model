"""E. Business cycle: leading vs coincident composites, recession odds, phase — or 'mixed' when evidence conflicts."""
from __future__ import annotations

import math
from statistics import mean, pstdev

import pandas as pd

from .signals import Signal, chg_z, level_z, missing

# (id, label, how, polarity, periods) — how: 'chg' = z of % change, 'diff' = z of change, 'level' = z of level
LEADING = [
    ("PERMIT", "Housing permits", "chg", 1, 6), ("NEWORDER", "Business equipment orders", "chg", 1, 6),
    ("ICSA", "Jobless claims (inverted)", "chg", -1, 13), ("AWHMAN", "Factory hours", "diff", 1, 6),
    ("T10Y3M", "Yield curve", "level", 1, 0), ("GACDFSA066MSFRBPHI", "Philly Fed survey", "level", 1, 0),
    ("GACDISA066MSFRBNY", "Empire survey", "level", 1, 0), ("UMCSENT", "Consumer sentiment", "diff", 1, 6),
    ("BAA10Y", "Credit spread (inverted)", "level", -1, 0), ("TEMPHELPS", "Temp jobs", "chg", 1, 6),
]
COINCIDENT = [
    ("PAYEMS", "Payrolls", "chg", 1, 6), ("INDPRO", "Industrial output", "chg", 1, 6),
    ("PCEC96", "Real consumer spending", "chg", 1, 6), ("DSPIC96", "Real disposable income", "chg", 1, 6),
    ("CFNAIMA3", "Chicago Fed activity (3m)", "level", 1, 0), ("RRSFS", "Real retail sales", "chg", 1, 6),
]
MIXED_THRESHOLD = 1.1


def recession_prob(spread_10y3m: float) -> float:
    """NY Fed probit: P(recession in 12 months) = Φ(−0.5333 − 0.6330 × spread), in %."""
    x = -0.5333 - 0.6330 * spread_10y3m
    return 50 * (1 + math.erf(x / math.sqrt(2)))


def classify(leading: list[float], coincident: list[float], inflation_dir: float | None,
             threshold: float = MIXED_THRESHOLD) -> dict:
    lead = mean(leading) if leading else 0.0
    coin = mean(coincident) if coincident else 0.0
    disp = pstdev(leading + coincident) if len(leading + coincident) > 1 else 0.0
    if coin >= 0 and lead >= 0:
        phase = "expansion"
    elif coin >= 0 and lead < 0:
        phase = "late cycle / slowing"
    elif coin < 0 and lead < 0:
        phase = "contraction"
    else:
        phase = "early recovery"
    conflict = (lead * coin < 0) and min(abs(lead), abs(coin)) > 0.5
    mixed = disp > threshold or conflict
    if inflation_dir is None:
        quadrant = "n/a"
    else:
        quadrant = {(True, True): "reflation (growth ↑, inflation ↑)", (True, False): "goldilocks (growth ↑, inflation ↓)",
                    (False, True): "stagflation risk (growth ↓, inflation ↑)",
                    (False, False): "disinflationary slowdown (growth ↓, inflation ↓)"}[(lead >= 0, inflation_dir >= 0)]
    return {"phase": phase, "mixed": bool(mixed), "dispersion": round(disp, 2), "leading": round(lead, 2),
            "coincident": round(coin, 2), "quadrant": quadrant}


def _component(ctx, sid, label, how, pol, periods) -> dict | None:
    if sid not in ctx.registry or not ctx.has(sid):
        return None
    summ = ctx.summary(sid)
    if summ["freshness"] not in ("fresh", "due"):
        return {"id": sid, "label": label, "z": None, "note": f"{summ['freshness']} (last {summ['obs_date']})"}
    s = ctx.s(sid)
    if ctx.registry[sid].freq == "D":
        s = s.resample("ME").mean()
    z = level_z(s) if how == "level" else chg_z(s, periods, pct=(how == "chg"))
    if z is None:
        return None
    z = max(-3, min(3, z * pol))
    return {"id": sid, "label": label, "z": round(z, 2), "obs_date": summ["obs_date"], "note": ""}


def assess(ctx, inflation_dir: float | None = None) -> dict:
    lead = [c for c in (_component(ctx, *x) for x in LEADING) if c]
    coin = [c for c in (_component(ctx, *x) for x in COINCIDENT) if c]
    lz = [c["z"] for c in lead if c["z"] is not None]
    cz = [c["z"] for c in coin if c["z"] is not None]
    cls = classify(lz, cz, inflation_dir)
    sig = []
    sig.append(Signal("leading_index", "Leading indicators", cls["leading"] * 1.5, horizon="leading", group="growth",
                      kind="estimate", evidence=f"{len(lz)} leading indicators average {cls['leading']:+.2f} (z-score)."))
    sig.append(Signal("coincident_index", "Current activity", cls["coincident"] * 1.5, horizon="coincident",
                      group="growth", kind="estimate", evidence=f"{len(cz)} activity indicators average {cls['coincident']:+.2f}."))
    rp = None
    if ctx.has("T10Y3M"):
        raw = ctx.s("T10Y3M").dropna()
        m = raw.groupby(raw.index.to_period("M")).mean()
        m.index = raw.groupby(raw.index.to_period("M")).apply(lambda x: x.index[-1]).values  # label = last real obs
        rp = recession_prob(float(m.iloc[-1]))
        ctx.put("RECESSION_PROB_CURVE", m.apply(recession_prob))
        sig.append(Signal("curve_recession", "Recession odds from the yield curve", (25 - rp) / 12.5, horizon="leading",
                          group="growth", kind="estimate",
                          evidence=f"10y−3m spread {m.iloc[-1]:+.2f}pp → {rp:.0f}% odds of recession within 12 months "
                                   "(NY Fed model; slow and imperfect since 2022)."))
    else:
        sig.append(missing("curve_recession", "Recession odds", "growth", "no yield curve"))
    if ctx.has("SAHMREALTIME"):
        s = ctx.summary("SAHMREALTIME")
        sig.append(Signal("sahm", "Sahm rule", (0.3 - s["latest"]) * 4, horizon="coincident", group="labour",
                          evidence=f"Sahm indicator {s['latest']:.2f} (recession signal at 0.50)."))
    evidence = []
    for sid, label in (("GDPC1", "Real GDP"), ("PNFIC1", "Real business investment"), ("CP", "Corporate profits"),
                       ("ISRATIO", "Inventory/sales"), ("HOUST", "Housing starts"), ("PCESC96", "Real services spending")):
        if sid in ctx.registry and ctx.has(sid):
            s = ctx.summary(sid)
            evidence.append({"id": sid, "label": label, "latest": s["latest"], "yoy": s["yoy"], "obs_date": s["obs_date"],
                             "freshness": s["freshness"], "units": s["units"]})
    gdp_q = None
    if ctx.has("GDPC1"):
        g = ctx.s("GDPC1")
        gdp_q = float(((g.iloc[-1] / g.iloc[-2]) ** 4 - 1) * 100) if len(g) > 1 else None
    label = cls["phase"] + (" — mixed signals" if cls["mixed"] else "")
    charts = [
        {"id": "cy_curve", "title": "Yield curve: 10-year minus 3-month", "units": "percentage points", "start": "1985-01-01",
         "series": [{"key": "T10Y3M", "label": "10y − 3m"}], "source": "Federal Reserve H.15 (via FRED)", "recessions": True,
         "note": "Below 0 = inverted"},
        {"id": "cy_recprob", "title": "Recession odds from the yield curve", "units": "% chance within 12 months", "start": "1985-01-01",
         "series": [{"key": "RECESSION_PROB_CURVE", "label": "Recession odds"}], "source": "NY Fed probit model, recomputed",
         "recessions": True},
        {"id": "cy_activity", "title": "Activity: Chicago Fed index (0 = trend growth)", "units": "index", "start": "1990-01-01",
         "series": [{"key": "CFNAIMA3", "label": "3-month average"}], "source": "Chicago Fed (via FRED)", "recessions": True},
        {"id": "cy_orders", "title": "Leading: permits and equipment orders", "units": "% y/y", "start": "2000-01-01",
         "series": [{"key": "PERMIT", "label": "Housing permits", "transform": "yoy"},
                    {"key": "NEWORDER", "label": "Core capital goods orders", "transform": "yoy"}],
         "source": "Census (via FRED)", "recessions": True},
    ]
    return {"classification": cls, "label": label, "recession_prob": rp, "gdp_qoq_ann": gdp_q,
            "leading": lead, "coincident": coin, "evidence": evidence, "signals": sig, "charts": charts}
