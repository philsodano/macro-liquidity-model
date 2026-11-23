"""Downloadable research files: Damodaran implied equity risk premium (monthly)."""
from __future__ import annotations

import io
import warnings
from datetime import date

import pandas as pd

from ..http import get

DAMODARAN = "https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbymonth.xlsx"
SHILLER = "https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/ie_data.xls"


def parse_shiller(content: bytes, column: str) -> pd.Series:
    df = pd.read_excel(io.BytesIO(content), sheet_name="Data", header=7)
    d = pd.to_numeric(df["Date"], errors="coerce")
    df = df[d.notna()]
    d = d[d.notna()]
    # Shiller dates are YYYY.MM (October = 2024.1)
    years = d.astype(int)
    months = ((d - years) * 100).round().astype(int)
    idx = pd.to_datetime(dict(year=years, month=months, day=1))
    s = pd.Series(pd.to_numeric(df[column], errors="coerce").values, index=idx)
    return s.dropna().astype(float).sort_index()


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
    if ind.source_id.startswith("shiller:"):
        return parse_shiller(get(SHILLER).content, ind.source_id.split(":", 1)[1]) * ind.scale
    raise ValueError(f"unknown file source {ind.source_id}")
