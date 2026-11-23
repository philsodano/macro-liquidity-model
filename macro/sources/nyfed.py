"""NY Fed research data files: ACM Treasury term premium."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from ..http import get

ACM = "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls"


def parse_acm(content: bytes, column: str, sheet: str = "ACM Daily") -> pd.Series:
    df = pd.read_excel(io.BytesIO(content), sheet_name=sheet)
    s = pd.Series(pd.to_numeric(df[column], errors="coerce").values,
                  index=pd.to_datetime(df["DATE"], format="%d-%b-%Y"))
    return s.dropna().astype(float).sort_index()


def fetch(ind, start: date | None = None) -> pd.Series:
    s = parse_acm(get(ACM).content, ind.source_id, ind.params.get("sheet", "ACM Daily"))
    if start:
        s = s[s.index >= pd.Timestamp(start)]
    return s * ind.scale
