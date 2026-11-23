"""US Treasury Fiscal Data API: daily TGA (DTS) and marketable debt by type (MSPD)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..http import get

BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_dts_tga(rows: list[dict]) -> pd.Series:
    out = {}
    for r in rows:
        if "TGA" in r["account_type"] and "Closing Balance" in r["account_type"]:
            v = _num(r.get("close_today_bal"))
            v = v if v is not None else _num(r.get("open_today_bal"))
            if v is not None:
                out[pd.Timestamp(r["record_date"])] = v
    return pd.Series(out, dtype=float).sort_index()


def parse_mspd(rows: list[dict], cls: str) -> pd.Series:
    out = {}
    for r in rows:
        name = r["security_type_desc"] if cls.startswith("Total") else r["security_class_desc"]
        if name == cls and (cls.startswith("Total") or r["security_type_desc"] == "Marketable"):
            v = _num(r["total_mil_amt"])
            if v is not None:
                out[pd.Timestamp(r["record_date"])] = v
    return pd.Series(out, dtype=float).sort_index()


def _pages(endpoint: str, params: dict) -> list[dict]:
    rows, page = [], 1
    while True:
        p = dict(params, **{"page[size]": 10000, "page[number]": page})
        j = get(f"{BASE}/{endpoint}", params=p).json()
        rows += j["data"]
        if page >= j.get("meta", {}).get("total-pages", 1):
            return rows
        page += 1


def fetch(ind, start: date | None = None) -> pd.Series:
    kind, _, arg = ind.source_id.partition(":")
    since = pd.Timestamp(start or "2005-01-01").strftime("%Y-%m-%d")
    if kind == "dts":
        rows = _pages("v1/accounting/dts/operating_cash_balance",
                      {"filter": f"record_date:gte:{since}", "fields": "record_date,account_type,close_today_bal,open_today_bal"})
        s = parse_dts_tga(rows)
    elif kind == "mspd":
        rows = _pages("v1/debt/mspd/mspd_table_1",
                      {"filter": f"record_date:gte:{since}", "fields": "record_date,security_type_desc,security_class_desc,total_mil_amt"})
        s = parse_mspd(rows, arg)
    else:
        raise ValueError(f"unknown treasury source_id {ind.source_id}")
    return s * ind.scale
