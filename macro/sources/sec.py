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
    df = _frame(units)
    out: dict[pd.Timestamp, float] = {}
    direct = df[(df["days"] >= 80) & (df["days"] <= 100)]
    for _, r in direct.iterrows():
        out[r["end"]] = float(r["val"])
    for start, g in df[df["days"] > 100].groupby("start"):
        g = g.sort_values("end")
        prev_end, prev_val = None, 0.0
        q1 = direct[direct["start"] == start]
        if not q1.empty:
            prev_end, prev_val = q1["end"].iloc[0], float(q1["val"].iloc[0])
        for _, r in g.iterrows():
            if prev_end is None:
                break
            if r["end"] not in out and 80 <= (r["end"] - prev_end).days <= 100:
                out[r["end"]] = float(r["val"]) - prev_val
            prev_end, prev_val = r["end"], float(r["val"])
    return pd.Series(out, dtype=float).sort_index()


def filed_dates(units: list[dict]) -> pd.Series:
    df = _frame(units)
    return df.groupby("end")["filed"].max()


def fetch(ind, start: date | None = None) -> pd.Series:
    cik, concept = ind.source_id.split(":")
    r = get(URL.format(cik=int(cik), concept=concept), descriptive_ua=True)
    units = r.json()["units"]["USD"]
    s = quarterly(units) * ind.scale
    if start:
        s = s[s.index >= pd.Timestamp(start)]
    return s
