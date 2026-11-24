import io

import pandas as pd
import pytest

from macro.sources import cftc, finra, nyfedpd, ofr

ROWS = [
    {"report_date_as_yyyy_mm_dd": "2026-11-17T00:00:00.000", "open_interest_all": "1000", "lev_money_positions_long": "300",
     "lev_money_positions_short": "100", "asset_mgr_positions_long": "500", "asset_mgr_positions_short": "50"},
    {"report_date_as_yyyy_mm_dd": "2026-11-10T00:00:00.000", "open_interest_all": "0", "lev_money_positions_long": "1",
     "lev_money_positions_short": "1", "asset_mgr_positions_long": "1", "asset_mgr_positions_short": "1"},
]


def test_cftc_net_pct_and_ls():
    assert cftc.parse(ROWS, "lev_net_pct").loc["2026-11-17"] == pytest.approx(20.0)
    assert cftc.parse(ROWS, "lev_ls").loc["2026-11-17"] == pytest.approx(3.0)
    assert cftc.parse(ROWS, "am_net_pct").loc["2026-11-17"] == pytest.approx(45.0)


def test_cftc_skips_zero_oi():
    s = cftc.parse(ROWS, "lev_net_pct")
    assert pd.Timestamp("2026-11-10") not in s.index and len(s) == 1


def test_ofr_parse():
    s = ofr.parse([["2026-03-31", 5140000000000.0], ["2026-06-30", 6194000000000.0], ["2026-09-30", None]])
    assert s.loc["2026-06-30"] == 6194000000000.0 and len(s) == 2


def test_nyfedpd_parse():
    p = {"pd": {"timeseries": [{"asofdate": "2026-11-12", "keyid": "PDPOSGST-TOT", "value": "108014"},
                               {"asofdate": "2026-11-05", "keyid": "PDPOSGST-TOT", "value": "*"}]}}
    s = nyfedpd.parse(p)
    assert s.loc["2026-11-12"] == 108014.0 and len(s) == 1


def _xlsx(cols: dict) -> bytes:
    b = io.BytesIO()
    pd.DataFrame(cols).to_excel(b, index=False)
    return b.getvalue()


def test_finra_parse_month_start():
    raw = _xlsx({"Year-Month": ["2026-10", "2026-09"], "Debit Balances in Customers' Securities Margin Accounts": [1448360, 1480054]})
    s = finra.parse(raw, "Debit Balances in Customers' Securities Margin Accounts")
    assert s.loc["2026-10-01"] == 1448360 and s.index.is_monotonic_increasing


def test_finra_missing_column_raises():
    raw = _xlsx({"Year-Month": ["2026-10"], "Something else": [1]})
    with pytest.raises(ValueError):
        finra.parse(raw, "Debit Balances in Customers' Securities Margin Accounts")
