"""Downloadable research files: Damodaran implied equity risk premium (monthly)."""
from __future__ import annotations

import io
import warnings
from datetime import date

import pandas as pd

from ..http import get

DAMODARAN = "https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbymonth.xlsx"


def parse_damodaran(content: bytes, column: str) -> pd.Series:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = pd.read_excel(io.BytesIO(content), sheet_name="Historical ERP")
    df = df[pd.to_datetime(df["Start of month"], errors="coerce").notna()]
    s = pd.Series(pd.to_numeric(df[column], errors="coerce").values, index=pd.to_datetime(df["Start of month"]))
    return (s.dropna() * 100).astype(float).sort_index()  # percent


def fetch(ind, start: date | None = None) -> pd.Series:
    if ind.source_id.startswith("damodaran:"):
        return parse_damodaran(get(DAMODARAN).content, ind.source_id.split(":", 1)[1]) * ind.scale
    raise ValueError(f"unknown file source {ind.source_id}")
