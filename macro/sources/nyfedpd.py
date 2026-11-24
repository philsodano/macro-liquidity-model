"""NY Fed Primary Dealer Statistics (weekly dealer positions)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..http import get

URL = "https://markets.newyorkfed.org/api/pd/get/{key}.json"


def parse(payload: dict) -> pd.Series:
    out = {}
    for r in payload["pd"]["timeseries"]:
        try:
            out[pd.Timestamp(r["asofdate"])] = float(r["value"])
        except (TypeError, ValueError):
            continue  # '*' = suppressed / not available
    return pd.Series(out, dtype=float).sort_index()


def fetch(ind, start: date | None = None) -> pd.Series:
    s = parse(get(URL.format(key=ind.source_id)).json()) * ind.scale
    return s[s.index >= pd.Timestamp(start)] if start else s
