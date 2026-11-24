import json

from macro.render.dashboard import TABS, render_dashboard

SNAP = {"meta": {"as_of": "2026-11-23"}, "charts": [], "series": {}}


def test_render_contains_all_tabs(tmp_path):
    out = render_dashboard(SNAP, reports=[{"date": "2026-11-27", "title": "Week 48", "html": "<p>x</p>"}], out_dir=tmp_path)
    html = out.read_text()
    for tab_id, label in TABS:
        assert f'href="#{tab_id}"' in html and label in html
    assert "<title>" in html and "snapshot.json" in html
    assert json.loads((tmp_path / "reports.json").read_text())[0]["date"] == "2026-11-27"
    assert json.loads((tmp_path / "snapshot.json").read_text())["meta"]["as_of"] == "2026-11-23"


def test_template_has_no_external_hosts_outside_allowlist(tmp_path):
    html = render_dashboard(SNAP, reports=[], out_dir=tmp_path).read_text()
    import re
    hosts = set(re.findall(r'(?:src|href)="https://([^/"]+)', html))
    assert hosts <= {"fonts.googleapis.com", "fonts.gstatic.com", "cdnjs.cloudflare.com"}, hosts


def test_no_dual_axis_charts():
    from datetime import date
    from macro.registry import load_registry, load_settings
    from macro.snapshot import build_snapshot
    from macro.store import Store
    snap = build_snapshot(Store(), load_registry(), load_settings(), today=date(2026, 11, 23), write=False, research=False)
    for c in snap["charts"]:
        assert all("axis" not in s for s in c["series"]), c["id"]


def test_snapshot_has_positioning():
    from datetime import date
    from macro.registry import load_registry, load_settings
    from macro.snapshot import build_snapshot
    from macro.store import Store
    snap = build_snapshot(Store(), load_registry(), load_settings(), today=date(2026, 11, 24), write=False, research=False)
    pos = snap["positioning"]
    for k in ("hedge_funds", "futures", "leverage", "banks", "options", "signals", "summary"):
        assert k in pos
    assert any(c["section"] == "positioning" for c in snap["charts"])
    assert "positioning" in snap["scenarios"]["group_scores"]


def test_liquidity_charts_have_explanations():
    import json
    from pathlib import Path
    from datetime import date
    from macro.registry import load_registry, load_settings
    from macro.snapshot import build_snapshot
    from macro.store import Store
    snap = build_snapshot(Store(), load_registry(), load_settings(), today=date(2026, 11, 24), write=False, research=False)
    liq = [c for c in snap["charts"] if c["section"] == "liquidity" or c["section"].startswith("pillar:")]
    assert len(liq) >= 14
    for c in liq:
        assert len(c.get("explain", "")) > 40, c["id"]
