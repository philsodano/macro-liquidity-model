"""FRED via the public CSV endpoint (no API key) and ALFRED for point-in-time vintages."""
from __future__ import annotations

import io
import re
from datetime import date, datetime

import pandas as pd

from ..http import get

CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
ALFRED = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"


def parse_csv(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text), dtype=str)
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna().astype(float)


def parse_updated(html: str) -> datetime | None:
    d = re.search(r'updated-date">\s*([A-Za-z]{3} \d{1,2}, \d{4})', html)
    if not d:
        return None
    t = re.search(r'updated-time">\s*(\d{1,2}:\d{2} [AP]M)', html)
    txt = d.group(1) + (" " + t.group(1) if t else " 12:00 AM")
    return datetime.strptime(txt, "%b %d, %Y %I:%M %p")


def fetch(ind, start: date | None = None) -> pd.Series:
    params = {"id": ind.source_id}
    if start:
        params["cosd"] = pd.Timestamp(start).strftime("%Y-%m-%d")
    s = parse_csv(get(CSV, params=params).text)
    return s * ind.scale


def last_updated(source_id: str) -> datetime | None:
    try:
        return parse_updated(get(f"https://fred.stlouisfed.org/series/{source_id}", retries=1).text)
    except RuntimeError:
        return None


def fetch_vintage(source_id: str, vintage_date: date) -> pd.Series:
    """Series as it was published on vintage_date (ALFRED)."""
    params = {"id": source_id, "vintage_date": pd.Timestamp(vintage_date).strftime("%Y-%m-%d")}
    return parse_csv(get(ALFRED, params=params).text)
