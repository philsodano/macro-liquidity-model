from datetime import date

from macro import history


def rec(d, base, bull, bear, groups, regime="expansion"):
    return {"date": d, "scenarios": {"base": base, "bull": bull, "bear": bear}, "group_scores": groups,
            "regime": {"label": regime}, "liquidity": {"market": {"state": "neutral"}, "pillars": {}},
            "cross_asset": {}, "allocation": {}}


def test_append_and_previous(tmp_path):
    p = tmp_path / "c.jsonl"
    history.append(rec("2026-11-13", 55, 20, 25, {}), p)
    history.append(rec("2026-11-20", 50, 20, 30, {}), p)
    assert history.previous(p, before=date(2026, 11, 20))["date"] == "2026-11-13"
    assert history.previous(p, before=date(2026, 11, 13)) is None
    assert history.previous(tmp_path / "none.jsonl", before=date(2026, 11, 20)) is None


def test_append_replaces_same_date(tmp_path):
    p = tmp_path / "c.jsonl"
    history.append(rec("2026-11-20", 55, 20, 25, {}), p)
    history.append(rec("2026-11-20", 50, 20, 30, {}), p)
    assert len(history.load(p)) == 1 and history.load(p)[0]["scenarios"]["bear"] == 30


def test_diff_reports_prob_change_with_drivers():
    prev = rec("2026-11-13", 55, 20, 25, {"credit": 0.5, "liquidity": 0.2, "growth": 0.1})
    cur = rec("2026-11-20", 48, 17, 35, {"credit": -1.5, "liquidity": 0.1, "growth": 0.1}, regime="late cycle / slowing")
    d = history.diff(prev, cur)
    bear = next(x for x in d if x["field"] == "Bear case probability")
    assert bear["before"] == 25 and bear["after"] == 35 and "credit" in bear["why"].lower()
    assert any(x["field"] == "Cycle" for x in d)
    assert history.diff(None, cur) == []
