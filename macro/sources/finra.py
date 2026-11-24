"""FINRA margin statistics (monthly customer margin debt and free credit balances, USD mn)."""
from __future__ import annotations

import io
import warnings
from datetime import date

import pandas as pd

from ..http import get

URL = "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"


def parse(content: bytes, column: str) -> pd.Series:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = pd.read_excel(io.BytesIO(content))
    if "Year-Month" not in df.columns or column not in df.columns:
        raise ValueError(f"FINRA sheet layout changed: missing {column!r}")
    idx = pd.to_datetime(df["Year-Month"].astype(str).str[:7] + "-01", errors="coerce")
    s = pd.Series(pd.to_numeric(df[column], errors="coerce").values, index=idx)
    return s[s.index.notna()].dropna().astype(float).sort_index()


def fetch(ind, start: date | None = None) -> pd.Series:
    return parse(get(URL, descriptive_ua=True).content, ind.source_id) * ind.scale
