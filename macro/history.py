"""Dated record of model conclusions and what changed between runs."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .registry import ROOT

DEFAULT = ROOT / "history" / "conclusions.jsonl"
GROUP_NAMES = {"liquidity": "liquidity", "credit": "credit", "growth": "growth", "labour": "jobs",
               "consumer": "consumer", "inflation": "inflation", "policy": "Fed policy", "valuation": "valuation"}


def load(path: Path = DEFAULT) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def append(record: dict, path: Path = DEFAULT) -> None:
    """One record per date: a re-run on the same date replaces it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r for r in load(path) if r["date"] != record["date"]] + [record]
    rows.sort(key=lambda r: r["date"])
    path.write_text("".join(json.dumps(r, default=str, sort_keys=True) + "\n" for r in rows))


def previous(path: Path = DEFAULT, before: date | None = None) -> dict | None:
    rows = load(path)
    if before is not None:
        rows = [r for r in rows if r["date"] < before.isoformat()]
    return rows[-1] if rows else None


def _drivers(prev: dict, cur: dict, scen: str) -> str:
    pg, cg = prev.get("group_scores", {}), cur.get("group_scores", {})
    moves = sorted(((g, cg.get(g, 0) - pg.get(g, 0)) for g in set(pg) | set(cg)), key=lambda kv: -abs(kv[1]))
    moves = [(g, d) for g, d in moves if abs(d) >= 0.2][:3]
    if not moves:
        return "Small shifts across many signals."
    return "Driven by " + ", ".join(f"{GROUP_NAMES.get(g, g)} {'improving' if d > 0 else 'weakening'} ({d:+.1f})"
                                    for g, d in moves) + "."


def diff(prev: dict | None, cur: dict) -> list[dict]:
    if not prev:
        return []
    out = []
    for k, label in (("base", "Base case probability"), ("bull", "Bull case probability"), ("bear", "Bear case probability")):
        a, b = prev["scenarios"].get(k), cur["scenarios"].get(k)
        if a is not None and b is not None and abs(b - a) >= 2:
            out.append({"field": label, "before": a, "after": b, "why": _drivers(prev, cur, k)})
    if prev.get("regime", {}).get("label") != cur.get("regime", {}).get("label"):
        out.append({"field": "Cycle", "before": prev["regime"].get("label"), "after": cur["regime"].get("label"),
                    "why": "Leading/coincident indicator balance shifted."})
    pl, cl = prev.get("liquidity", {}), cur.get("liquidity", {})
    for key, label in (("market", "Market liquidity"), ("economy", "Economy liquidity")):
        a, b = pl.get(key, {}).get("state"), cl.get(key, {}).get("state")
        if a and b and a != b:
            out.append({"field": label, "before": a, "after": b, "why": f"Impulse now {cl[key].get('composite')}."})
    for pid, p in cl.get("pillars", {}).items():
        q = pl.get("pillars", {}).get(pid)
        if q and (q.get("state") != p.get("state") or q.get("trend") != p.get("trend")):
            out.append({"field": f"{p.get('title', pid)}", "before": f"{q.get('state')}, {q.get('trend')}",
                        "after": f"{p.get('state')}, {p.get('trend')}", "why": f"Impulse {q.get('impulse')} → {p.get('impulse')}."})
    for xid, v in cur.get("cross_asset", {}).items():
        a = prev.get("cross_asset", {}).get(xid)
        if a and a != v:
            out.append({"field": f"Cross-asset: {xid.replace('_', ' ')}", "before": a, "after": v, "why": ""})
    for asset, v in cur.get("allocation", {}).items():
        a = prev.get("allocation", {}).get(asset)
        if a and a.get("stance") != v.get("stance"):
            out.append({"field": f"Outlook: {asset}", "before": a["stance"], "after": v["stance"],
                        "why": f"Score {a.get('score')} → {v.get('score')}."})
    for key, label in (("inflation_driver", "Inflation driver"), ("consumer", "Consumer funding")):
        if prev.get(key) and cur.get(key) and prev[key] != cur[key]:
            out.append({"field": label, "before": prev[key], "after": cur[key], "why": ""})
    return out
