import copy
import json
from pathlib import Path

import pytest

from macro.render.report import SECTIONS, render_report

SNAP = json.loads((Path(__file__).parent.parent / "site" / "snapshot.json").read_text())


def test_report_sections_in_order():
    rep = render_report(SNAP, None, None)
    pos = [rep["md"].index(f"## {i}. {s}") for i, s in enumerate(SECTIONS, 1)]
    assert pos == sorted(pos) and len(SECTIONS) == 8
    assert rep["date"] == SNAP["meta"]["as_of"] and "<h2>" in rep["html"]


def test_report_uses_same_snapshot_numbers():
    rep = render_report(SNAP, None, None)
    mk = SNAP["liquidity"]["consolidated"]["market"]["composite"]
    assert f"{mk:+.2f}" in rep["md"]
    f = SNAP["scenarios"]["final"]
    assert f"{f['base']:.0f}%" in rep["md"] and f"{f['bear']:.0f}%" in rep["md"]


def test_report_highlights_changes():
    prev = copy.deepcopy(SNAP)
    cur = copy.deepcopy(SNAP)
    cur["changes"] = {"previous_date": "2026-11-16", "items": [
        {"field": "Bear case probability", "before": 25, "after": 36, "why": "Driven by credit weakening (-1.5)."}]}
    rep = render_report(cur, prev, None)
    exec_part = rep["md"].split("## 2.")[0]
    assert "Bear case probability" in exec_part and "25 → 36" in exec_part


def test_report_includes_labelled_analyst_notes():
    notes = "## Liquidity Update\nTGA rebuild after the debt-ceiling deal is the swing factor.\n"
    rep = render_report(SNAP, None, notes)
    liq = rep["md"].split("## 2. Liquidity Update")[1].split("## 3.")[0]
    assert "Analyst interpretation" in liq and "TGA rebuild" in liq


def test_report_mentions_positioning():
    snap = copy.deepcopy(SNAP)
    snap["positioning"] = {"summary": "Positioning is crowded long.", "signals": []}
    rep = render_report(snap, None, None)
    fm = rep["md"].split("## 6. Financial Markets")[1].split("## 7.")[0]
    assert "Positioning" in fm and "crowded long" in fm
