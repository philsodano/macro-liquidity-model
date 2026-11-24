"""OFR Hedge Fund Monitor API: SEC Form PF aggregates (quarterly) and CFTC TFF aggregates (weekly)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..http import get

URL = "https://data.financialresearch.gov/hf/v1/series/timeseries"


def parse(payload: list) -> pd.Series:
    out = {pd.Timestamp(d): float(v) for d, v in payload if v is not None}
    return pd.Series(out, dtype=float).sort_index()


def fetch(ind, start: date | None = None) -> pd.Series:
    s = parse(get(URL, params={"mnemonic": ind.source_id}).json()) * ind.scale
    return s[s.index >= pd.Timestamp(start)] if start else s
