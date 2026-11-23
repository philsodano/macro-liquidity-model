"""SEC XBRL company concepts → quarterly flows (10-Q values are year-to-date; de-cumulate)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..http import get

URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{concept}.json"


def _frame(units: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(units)
    df = df[df.get("start").notna()] if "start" in df else df.iloc[0:0]
    df["start"] = pd.to_datetime(df["start"])
    df["end"] = pd.to_datetime(df["end"])
    df["filed"] = pd.to_datetime(df["filed"])
    df["days"] = (df["end"] - df["start"]).dt.days
    # latest filing wins for a given period (restatements)
    return df.sort_values("filed").drop_duplicates(["start", "end"], keep="last")


def quarterly(units: list[dict]) -> pd.Series:
    """Quarterly flows from a mix of 3-month and year-to-date facts.

    Direct ~90-day facts are used as-is; otherwise consecutive YTD facts sharing a fiscal-year start are
    differenced. A quarter with no direct fact and no prior YTD anchor stays missing (never assumed zero)."""
    df = _frame(units)
    out: dict[pd.Timestamp, float] = {}
    for _, r in df[(df["days"] >= 80) & (df["days"] <= 100)].iterrows():
        out[r["end"]] = float(r["val"])
    for _, g in df.groupby("start"):
        g = g.sort_values("end").reset_index(drop=True)
        for i in range(1, len(g)):
            cur, prev = g.iloc[i], g.iloc[i - 1]
            if cur["end"] not in out and 80 <= (cur["end"] - prev["end"]).days <= 100:
                out[cur["end"]] = float(cur["val"]) - float(prev["val"])
    s = pd.Series(out, dtype=float)
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()


def filed_dates(units: list[dict]) -> pd.Series:
    df = _frame(units)
    return df.groupby("end")["filed"].max()


def fetch(ind, start: date | None = None) -> pd.Series:
    """source_id = 'CIK:ConceptA|ConceptB' — concepts tried in order, earlier ones win on overlapping dates."""
    cik, concepts = ind.source_id.split(":")
    parts, errors = [], []
    for concept in concepts.split("|"):
        try:
            r = get(URL.format(cik=int(cik), concept=concept), descriptive_ua=True, retries=2)
            parts.append(quarterly(r.json()["units"]["USD"]))
        except RuntimeError as e:
            errors.append(str(e))
    if not parts:
        raise RuntimeError("; ".join(errors))
    s = parts[0]
    for p in parts[1:]:
        s = s.combine_first(p)
    s = s * ind.scale
    if start:
        s = s[s.index >= pd.Timestamp(start)]
    return s
