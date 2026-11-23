"""Bank of England Interactive Database (IADB) CSV."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from ..http import get

URL = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"


def parse(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(df.iloc[:, 0], format="%d %b %Y")
    return s.dropna().astype(float).sort_index()


def fetch(ind, start: date | None = None) -> pd.Series:
    params = {"csv.x": "yes", "Datefrom": pd.Timestamp(start or "1990-01-01").strftime("%d/%b/%Y"),
              "Dateto": "now", "SeriesCodes": ind.source_id, "CSVF": "TN", "UsingCodes": "Y", "VPD": "Y", "VFD": "N"}
    return parse(get(URL, params=params, descriptive_ua=True).text) * ind.scale  # BoE rejects library UAs
