"""One JSON snapshot per run — the single source of truth for the dashboard and the weekly report."""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import history, narrative, research as research_mod, scenarios
from .analytics import assess_all as analytics_all
from .context import Ctx
from .liquidity import assess_all as liquidity_all
from .registry import ROOT
from .transforms import ann_rate, yoy

SCHEMA = 1


def clean(o):
    """Make anything JSON-safe: drop pandas objects, NaN → None, numpy → python."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items() if not isinstance(v, (pd.Series, pd.DataFrame))}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if hasattr(o, "to_dict") and not isinstance(o, (pd.Series, pd.DataFrame)):
        return clean(o.to_dict())
    if isinstance(o, (np.floating, float)):
        return None if math.isnan(o) or math.isinf(o) else round(float(o), 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return o.strftime("%Y-%m-%d")
    return o


def _downsample(s: pd.Series) -> pd.Series:
    s = s.dropna()
    if len(s) < 600:
        return s
    cut = s.index[-1] - pd.DateOffset(years=5)
    old, new = s[s.index < cut], s[s.index >= cut]
    # keep the last real observation in each bin, with its own date (a bin label could post-date the data)
    old = old.groupby(old.index.to_period("M")).tail(1)
    if len(new) > 400:
        new = new.groupby(new.index.to_period("W-FRI")).tail(1)
    return pd.concat([old, new])


def _sig(x: float) -> float:
    return float(f"{x:.5g}")


def chart_series(ctx, key: str, transform: str | None, start: str) -> pd.Series:
    s = ctx.s(key) if (key in ctx.registry or key in ctx.extra_series) else pd.Series(dtype=float)
    if s.empty:
        return s
    if transform == "yoy":
        s = yoy(s)
    elif transform == "ann3":
        s = ann_rate(s, 3)
    elif transform == "rebase":
        s = s[s.index >= pd.Timestamp(start)]
        s = s / s.iloc[0] * 100 if len(s) else s
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    return _downsample(s[s.index >= pd.Timestamp(start)])


def collect_charts(liq: dict, a: dict) -> list[dict]:
    charts = [
        {"id": "liq_split", "title": "Liquidity impulse: market vs economy", "units": "z-score (0 = normal)",
         "start": "2005-01-01", "section": "liquidity",
         "series": [{"key": "LIQ_MARKET", "label": "Market liquidity (Fed, global, credit)"},
                    {"key": "LIQ_ECONOMY", "label": "Economy liquidity (deficits, banks, AI)"}],
         "source": "Model estimate from Fed, Treasury, ECB, BoJ, FRED data", "note": "Above +0.5 = adding; below −0.5 = draining",
         "recessions": True},
        {"id": "liq_pillars", "title": "Liquidity impulse by pillar", "units": "z-score", "start": "2015-01-01",
         "section": "liquidity", "series": [{"key": f"IMPULSE_{p['id']}", "label": p["title"]} for p in liq["pillars"]],
         "source": "Model estimate"},
    ]
    for p in liq["pillars"]:
        for c in p["charts"]:
            charts.append({**c, "section": f"pillar:{p['id']}"})
    for sec, key in (("central_banks", "central_banks"), ("consumer", "consumer"), ("cycle", "cycle"),
                     ("inflation", "inflation"), ("markets", "markets")):
        for c in a[key]["charts"]:
            charts.append({**c, "section": sec})
    return charts


def data_quality(ctx) -> dict:
    rows, counts = [], {}
    for sid, ind in ctx.registry.items():
        if ind.source == "derived":
            continue
        s = ctx.summary(sid)
        m = ctx.store.meta(sid)
        status = s["freshness"] if not ind.unavailable else "unavailable"
        if status == "missing" and m.get("last_error"):
            status = "failed"
        counts[status] = counts.get(status, 0) + 1
        rows.append({"id": sid, "name": ind.name, "source": ind.source, "source_id": ind.source_id, "freq": ind.freq,
                     "units": ind.units, "obs_date": s["obs_date"], "first_seen": s["first_seen"], "status": status,
                     "last_fetch": m.get("last_fetch"), "error": (m.get("last_error") or ind.unavailable or "")[:160],
                     "signal": ind.signal, "kind": ind.kind, "section": ind.section})
    return {"counts": counts, "rows": rows, "pseudo_point_in_time": sorted(ctx.pseudo_pit)}


def recessions(ctx) -> list[list[str]]:
    if not ctx.has("USREC"):
        return []
    r = ctx.s("USREC")
    out, start = [], None
    for d, v in r.items():
        if v == 1 and start is None:
            start = d
        if v == 0 and start is not None:
            out.append([start.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")])
            start = None
    if start is not None:
        out.append([start.strftime("%Y-%m-%d"), r.index[-1].strftime("%Y-%m-%d")])
    return out


def conclusions_record(snap: dict) -> dict:
    liq = snap["liquidity"]
    return {
        "date": snap["meta"]["as_of"], "built_at": snap["meta"]["built_at"],
        "scenarios": snap["scenarios"]["final"], "model_scenarios": snap["scenarios"]["model"],
        "override": snap["scenarios"].get("override"), "group_scores": snap["scenarios"]["group_scores"],
        "regime": {"label": snap["cycle"]["label"], **snap["cycle"]["classification"]},
        "liquidity": {"composite": liq["consolidated"]["composite"],
                      "market": {k: liq["consolidated"]["market"].get(k) for k in ("composite", "state", "trend")},
                      "economy": {k: liq["consolidated"]["economy"].get(k) for k in ("composite", "state", "trend")},
                      "pillars": {p["id"]: {k: p.get(k) for k in ("title", "impulse", "state", "trend")} for p in liq["pillars"]}},
        "inflation_driver": snap["inflation"]["driver"], "consumer": snap["consumer"]["diagnosis"],
        "cross_asset": {x["id"]: x["verdict"] for x in snap["cross_asset"]},
        "allocation": {x["asset"]: {"score": x["score"], "stance": x["stance"]} for x in snap["allocation"]["assets"]},
        "thesis": snap["executive"]["thesis"],
    }


def build_snapshot(store, registry, settings, today: date, as_of: date | None = None, write: bool = True,
                   research: bool = True, root: Path | None = None) -> dict:
    root = Path(root) if root else ROOT
    ctx = Ctx(store, registry, today=today, as_of=as_of, settings=settings)
    run_date = ctx.today
    liq = liquidity_all(ctx)
    a = analytics_all(ctx, liq)
    res = research_mod.assess(ctx, n_boot=settings.get("research", {}).get("n_boot", 300)) if research else \
        {"analogues": {}, "lags": [], "principles": []}
    sc = scenarios.score(a["signals"], settings)
    ov_path = root / "history" / "overrides.json"
    overrides = json.loads(ov_path.read_text()) if ov_path.exists() else []
    sc = scenarios.with_override(sc, overrides, run_date.isoformat())
    charts = collect_charts(liq, a)
    series = {}
    for c in charts:
        for s in c["series"]:
            dk = s["key"] + (f":{s['transform']}" if s.get("transform") else "")
            s["data_key"] = dk
            if dk not in series:
                pts = chart_series(ctx, s["key"], s.get("transform"), c.get("start", "2000-01-01"))
                series[dk] = [[d.strftime("%Y-%m-%d"), _sig(v)] for d, v in pts.items()]
    good, bad = narrative.risk_lists(a)
    snap = {
        "schema_version": SCHEMA,
        "meta": {"as_of": run_date.isoformat(), "built_at": datetime.now().isoformat(timespec="seconds"),
                 "mode": "as_of" if as_of else "live", "recessions": recessions(ctx),
                 "note": ("As-of run: series without a vintage that old use today's data cut at the date it would have "
                          "been published; later revisions are not undone.") if as_of else ""},
        "liquidity": {"pillars": liq["pillars"], "consolidated": liq["consolidated"]},
        "central_banks": a["central_banks"], "consumer": a["consumer"], "cycle": a["cycle"],
        "inflation": a["inflation"], "markets": a["markets"], "cross_asset": a["cross_asset"],
        "allocation": a["allocation"], "signals": [s.to_dict() for s in a["signals"]],
        "scenarios": {**sc, "text": narrative.scenarios(liq, a, sc)},
        "research": res, "charts": charts, "series": series,
    }
    snap["executive"] = {"tiles": narrative.tiles(liq, a, sc), "thesis": narrative.thesis(liq, a, sc),
                         "risk_rewarded": good, "risk_not_rewarded": bad}
    snap = clean(snap)
    snap["data_quality"] = clean(data_quality(ctx))
    rec = conclusions_record(snap)
    hist_path = root / "history" / "conclusions.jsonl"
    prev = history.previous(hist_path, before=run_date)
    snap["changes"] = {"previous_date": prev["date"] if prev else None, "items": history.diff(prev, rec)}
    if write and not as_of:
        history.append(rec, hist_path)
        out = root / "site" / "snapshot.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snap, separators=(",", ":")))
        arch = root / "history" / "snapshots" / f"{run_date.isoformat()}.json"
        arch.parent.mkdir(parents=True, exist_ok=True)
        arch.write_text(json.dumps({k: v for k, v in snap.items() if k not in ("series", "charts")},
                                   separators=(",", ":")))
    return snap
