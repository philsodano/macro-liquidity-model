"""Base / bull / bear probabilities from evidence. Deterministic, auditable, bounded analyst override."""
from __future__ import annotations

import math
from collections import defaultdict

SCEN = ("base", "bull", "bear")


def group_scores(signals) -> tuple[dict, list[str]]:
    by, seen = defaultdict(list), set()
    for s in signals:
        seen.add(s.group)
        if s.available:
            by[s.group].append(s.score)
    scores = {g: round(sum(v) / len(v), 3) for g, v in by.items()}
    return scores, sorted(seen - set(scores))


def _bound(p: dict, floor: float, cap: float) -> dict:
    p = dict(p)
    for _ in range(20):
        tot = sum(p.values())
        p = {k: v * 100 / tot for k, v in p.items()}
        clipped = {k: min(cap, max(floor, v)) for k, v in p.items()}
        if all(abs(clipped[k] - p[k]) < 1e-9 for k in p):
            break
        fixed = {k for k in p if clipped[k] != p[k]}
        free = [k for k in p if k not in fixed]
        rest = 100 - sum(clipped[k] for k in fixed)
        ftot = sum(p[k] for k in free) or 1
        p = {k: (clipped[k] if k in fixed else p[k] * rest / ftot) for k in p}
    return {k: round(v, 1) for k, v in p.items()}


def score(signals, settings: dict) -> dict:
    cfg = settings["scenarios"]
    w, floor, cap = cfg["weights"], cfg.get("floor", 5), cfg.get("cap", 80)
    gs, missing = group_scores(signals)
    logit = {k: math.log(cfg["priors"][k]) for k in SCEN}
    contributions = []
    for g, v in sorted(gs.items()):
        eff = w.get(g, 0) * v
        logit["bull"] += eff
        logit["bear"] -= eff
        contributions.append({"group": g, "score": v, "bull": round(eff, 3), "bear": round(-eff, 3)})
    m = max(logit.values())
    raw = {k: math.exp(v - m) for k, v in logit.items()}
    tot = sum(raw.values())
    model = _bound({k: raw[k] / tot * 100 for k in SCEN}, floor, cap)
    contributions.sort(key=lambda c: -abs(c["bull"]))
    return {"model": model, "override": None, "final": model, "group_scores": gs, "missing_groups": missing,
            "contributions": contributions,
            "method": "log-odds = log(prior) ± weight × average signal score per evidence group (bull +, bear −); "
                      f"normalised, floor {floor}%, cap {cap}%. Groups without data contribute nothing."}


def apply_override(model: dict, override: dict) -> dict:
    deltas, reason = override.get("deltas", {}), (override.get("reason") or "").strip()
    if not reason:
        raise ValueError("override needs a written reason")
    if any(abs(v) > 10 for v in deltas.values()):
        raise ValueError("override limited to ±10pp per scenario")
    if abs(sum(deltas.values())) > 0.05:
        raise ValueError("override deltas must sum to zero")
    out = {k: round(model[k] + deltas.get(k, 0), 1) for k in model}
    if min(out.values()) < 0:
        raise ValueError("override would make a probability negative")
    return out


def with_override(result: dict, overrides: list[dict], as_of: str) -> dict:
    """Apply the override dated exactly as_of, if any (overrides are one-run judgements, not sticky)."""
    ov = next((o for o in overrides if o.get("date") == as_of), None)
    if ov:
        result = dict(result, override=ov, final=apply_override(result["model"], ov))
    return result
