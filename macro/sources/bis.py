"""BIS statistics API (SDMX, CSV) — global liquidity indicators."""
from __future__ import annotations

from datetime import date

from ..http import get
from .ecb import parse

URL = "https://stats.bis.org/api/v1/data/{key}/all"


def fetch(ind, start: date | None = None):
    return parse(get(URL.format(key=ind.source_id), params={"format": "csv"}).text) * ind.scale
