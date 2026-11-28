"""Model shift approved 2026-11-28: payrolls, CPI and the Fed dot plot weigh more; consumer confidence less."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from macro.analytics import central_banks, consumer, cycle, inflation
from macro.context import Ctx
from macro.registry import load_registry, load_settings
from macro.store import Store

SEEN = date(2026, 11, 27)


def _ctx(tmp_path, today=date(2026, 11, 28)):
    return Ctx(Store(tmp_path), load_registry(), today=today, settings=load_settings())


def test_weights_in_settings():
    w = load_settings()["scenarios"]["weights"]
    assert w["jobs_report"] == 0.5 and w["inflation"] == 0.4 and w["policy"] == 0.4


def test_jobs_report_signal(tmp_path):
    ctx = _ctx(tmp_path)
    idx = pd.date_range("2023-01-01", "2026-10-01", freq="MS")
    ctx.store.write("PAYEMS", pd.Series(150000 + 200.0 * np.arange(len(idx)), index=idx), SEEN)
    sig = {s.id: s for s in consumer.assess(ctx)["signals"]}
    assert "payrolls" not in sig
    jr = sig["jobs_report"]
    assert jr.group == "jobs_report" and jr.score > 0.5 and "200k" in jr.evidence


def test_core_cpi_signal(tmp_path):
    ctx = _ctx(tmp_path)
    idx = pd.date_range("2023-01-01", "2026-10-01", freq="MS")
    ctx.store.write("CPILFESL", pd.Series(300 * 1.004 ** np.arange(len(idx)), index=idx), SEEN)  # ~4.9% a year
    sig = {s.id: s for s in inflation.assess(ctx)["signals"]}
    assert sig["core_cpi"].group == "inflation" and sig["core_cpi"].score < -1


def test_fed_path_signal(tmp_path):
    ctx = _ctx(tmp_path)
    st = ctx.store
    st.write("FEDTARMD", pd.Series([4.1, 4.1, 3.9, 3.6], index=pd.to_datetime(["2026-01-01", "2027-01-01", "2028-01-01", "2029-01-01"])), SEEN)
    st.write("FEDTARMDLR", pd.Series([3.1, 3.2], index=pd.to_datetime(["2026-06-17", "2026-09-16"])), SEEN)
    d = pd.bdate_range("2026-01-02", "2026-11-27")
    st.write("DFF", pd.Series(3.88, index=d), SEEN)
    st.write("DGS1", pd.Series(4.62, index=d), SEEN)
    st.write("DGS2", pd.Series(4.76, index=d), SEEN)
    out = central_banks.assess(ctx)
    fp = {s.id: s for s in out["signals"]}["fed_path"]
    assert fp.group == "policy" and "2027" in fp.evidence and "4.10%" in fp.evidence
    assert out["dots"]["next_year"] == 2027 and out["dots"]["median_next"] == pytest.approx(4.1)


def test_consumer_confidence_half_weight():
    assert cycle.WEIGHTS["UMCSENT"] == 0.5
    out = cycle.classify([2.0, 0.0], [0.0], 0.0, lead_weights=[0.5, 1.0])
    assert out["leading"] == pytest.approx(0.67, abs=0.01)
