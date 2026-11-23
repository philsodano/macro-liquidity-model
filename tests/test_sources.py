import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from macro.sources import boe, ecb, fred, sec, tiingo, treasury

FX = Path(__file__).parent / "fixtures"


def test_fred_csv_parse_drops_missing():
    s = fred.parse_csv((FX / "fred.csv").read_text())
    assert list(s.index.strftime("%Y-%m-%d")) == ["2026-01-01", "2026-03-01"]
    assert list(s.values) == [1.5, 2.0]


def test_fred_last_updated():
    assert fred.parse_updated((FX / "fred_page.html").read_text()) == datetime(2026, 11, 6, 9, 43)


def test_sec_decumulates_ytd():
    units = json.loads((FX / "sec_concept.json").read_text())["units"]["USD"]
    q = sec.quarterly(units)
    assert list(q.index.strftime("%Y-%m-%d")) == ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
    assert list(q.values) == [10, 15, 25, 30]


def test_sec_filed_dates():
    units = json.loads((FX / "sec_concept.json").read_text())["units"]["USD"]
    filed = sec.filed_dates(units)
    assert filed[pd.Timestamp("2025-12-31")] == pd.Timestamp("2026-02-01")


def test_tiingo_parse_uses_adjclose():
    s = tiingo.parse(json.loads((FX / "tiingo.json").read_text()))
    assert s.loc["2026-11-20"] == 603.4 and len(s) == 2


def test_treasury_mspd_class():
    rows = json.loads((FX / "mspd.json").read_text())["data"]
    s = treasury.parse_mspd(rows, "Bills")
    assert s.loc["2026-10-31"] == 7381670.6965 and s.loc["2026-09-30"] == 7300000.0
    assert treasury.parse_mspd(rows, "Total Marketable").loc["2026-10-31"] == 32150190.74


def test_treasury_dts_closing_balance_from_open_column():
    rows = json.loads((FX / "dts.json").read_text())["data"]
    s = treasury.parse_dts_tga(rows)
    assert s.loc["2026-11-19"] == 870001 and s.loc["2026-11-18"] == 892310 and len(s) == 2


def test_boe_parse():
    s = boe.parse((FX / "boe.csv").read_text())
    assert s.loc["2024-01-03"] == 5.25


def test_ecb_parse():
    s = ecb.parse((FX / "ecb.csv").read_text())
    assert s.loc["2026-11-14"] == 6190000
