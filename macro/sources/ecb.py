"""ECB Data Portal (SDMX REST, csvdata)."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from ..http import get

URL = "https://data-api.ecb.europa.eu/service/data/{key}"


def _dates(periods: pd.Series) -> pd.DatetimeIndex:
    p = periods.astype(str)
    if p.str.contains("-W").any():
        return pd.to_datetime(p + "-5", format="%G-W%V-%u")  # week -> Friday
    if p.str.contains("-Q").any():
        return pd.PeriodIndex(p.str.replace("-", ""), freq="Q").to_timestamp(how="end").normalize()
    return pd.to_datetime(p)


def parse(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    s = pd.Series(pd.to_numeric(df["OBS_VALUE"], errors="coerce").values, index=_dates(df["TIME_PERIOD"]))
    return s.dropna().astype(float).sort_index()


def fetch(ind, start: date | None = None) -> pd.Series:
    params = {"format": "csvdata"}
    if start:
        params["startPeriod"] = pd.Timestamp(start).strftime("%Y-%m-%d")
    return parse(get(URL.format(key=ind.source_id), params=params).text) * ind.scale
