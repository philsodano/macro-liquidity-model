"""Tiingo daily prices. The key is injected by the session proxy; the code never holds it."""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..http import get

URL = "https://api.tiingo.com/tiingo/daily/{ticker}/prices"


def parse(rows: list[dict]) -> pd.Series:
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    s = pd.Series(df["adjClose"].astype(float).values,
                  index=pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize())
    return s.sort_index()


def fetch(ind, start: date | None = None) -> pd.Series:
    params = {"startDate": pd.Timestamp(start or "1990-01-01").strftime("%Y-%m-%d"), "format": "json"}
    r = get(URL.format(ticker=ind.source_id), params=params,
            headers={"Authorization": "Token proxy-injected"}, retries=2)
    return parse(r.json()) * ind.scale
