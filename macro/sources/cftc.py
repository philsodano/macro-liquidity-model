"""CFTC Traders in Financial Futures (weekly; Tuesday positions, released Friday) via the CFTC Socrata API."""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..http import get

URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
GROUPS = {"lev": ("lev_money_positions_long", "lev_money_positions_short"),
          "am": ("asset_mgr_positions_long", "asset_mgr_positions_short")}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse(rows: list[dict], metric: str) -> pd.Series:
    """metric: '<group>_net_pct' = (long − short) ÷ open interest × 100, or '<group>_ls' = long ÷ short."""
    group, _, kind = metric.partition("_")
    lk, sk = GROUPS[group]
    out = {}
    for r in rows:
        oi, lo, sh = _f(r.get("open_interest_all")), _f(r.get(lk)), _f(r.get(sk))
        if lo is None or sh is None:
            continue
        if kind == "net_pct":
            if not oi:
                continue
            v = (lo - sh) / oi * 100
        elif kind == "ls":
            if not sh:
                continue
            v = lo / sh
        else:
            raise ValueError(f"unknown CFTC metric {metric}")
        out[pd.Timestamp(r["report_date_as_yyyy_mm_dd"][:10])] = v
    return pd.Series(out, dtype=float).sort_index()


def fetch(ind, start: date | None = None) -> pd.Series:
    code, metric = ind.source_id.split(":")
    since = pd.Timestamp(start or "2006-01-01").strftime("%Y-%m-%d")
    params = {"$where": f"cftc_contract_market_code='{code}' AND report_date_as_yyyy_mm_dd >= '{since}'",
              "$order": "report_date_as_yyyy_mm_dd", "$limit": 5000,
              "$select": "report_date_as_yyyy_mm_dd,open_interest_all," + ",".join(sum(GROUPS.values(), ()))}
    return parse(get(URL, params=params).json(), metric) * ind.scale
