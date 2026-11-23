"""Liquidity engine: six pillars + consolidation."""
from __future__ import annotations

from . import ai_capex, banking, central_bank, consolidate, fiscal, global_liq, private_credit

PILLAR_MODULES = [central_bank, fiscal, banking, private_credit, global_liq, ai_capex]


def assess_all(ctx) -> dict:
    pillars = [m.assess(ctx) for m in PILLAR_MODULES]
    comp = consolidate.consolidate(pillars)
    ctx.put("LIQ_COMPOSITE", comp["composite_history"])
    return {"pillars": pillars, "consolidated": comp}
