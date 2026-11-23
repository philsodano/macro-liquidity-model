import pytest

from macro import scenarios
from macro.analytics.signals import Signal

SETTINGS = {"scenarios": {"priors": {"base": 55, "bull": 20, "bear": 25}, "floor": 5, "cap": 80,
                          "weights": {"liquidity": 0.6, "credit": 0.5, "growth": 0.4, "labour": 0.3, "consumer": 0.3,
                                      "inflation": 0.3, "policy": 0.3, "valuation": 0.3}}}


def sig(group, score, available=True):
    return Signal(id=f"{group}{score}", label=group, score=score, evidence="", group=group, available=available)


def test_probs_sum_to_100():
    out = scenarios.score([sig("liquidity", 1.0), sig("credit", -0.5), sig("growth", 0.2)], SETTINGS)
    assert sum(out["final"].values()) == pytest.approx(100, abs=0.1)
    assert set(out["final"]) == {"base", "bull", "bear"}


def test_neutral_evidence_returns_priors():
    out = scenarios.score([], SETTINGS)
    assert out["final"] == {"base": 55.0, "bull": 20.0, "bear": 25.0}


def test_bullish_evidence_raises_bull():
    out = scenarios.score([sig(g, 1.5) for g in SETTINGS["scenarios"]["weights"]], SETTINGS)
    assert out["final"]["bull"] > 20 and out["final"]["bear"] < 25


def test_floor_and_cap():
    out = scenarios.score([sig(g, -2.0) for g in SETTINGS["scenarios"]["weights"]] * 3, SETTINGS)
    assert min(out["final"].values()) >= 5 - 1e-9 and max(out["final"].values()) <= 80 + 1e-9
    assert sum(out["final"].values()) == pytest.approx(100, abs=0.1)


def test_scenarios_with_missing_evidence():
    with_missing = scenarios.score([sig("liquidity", 1.0), sig("credit", 0.0, available=False)], SETTINGS)
    without = scenarios.score([sig("liquidity", 1.0)], SETTINGS)
    assert with_missing["final"] == without["final"]
    assert "credit" in with_missing["missing_groups"]


def test_override_bounds():
    model = {"base": 50.0, "bull": 20.0, "bear": 30.0}
    ok = scenarios.apply_override(model, {"date": "2026-11-27", "deltas": {"bear": 5, "base": -5}, "reason": "x"})
    assert ok == {"base": 45.0, "bull": 20.0, "bear": 35.0}
    with pytest.raises(ValueError):
        scenarios.apply_override(model, {"date": "2026-11-27", "deltas": {"bear": 11, "base": -11}, "reason": "x"})
    with pytest.raises(ValueError):
        scenarios.apply_override(model, {"date": "2026-11-27", "deltas": {"bear": 5, "base": -5}, "reason": ""})
    with pytest.raises(ValueError):
        scenarios.apply_override(model, {"date": "2026-11-27", "deltas": {"bear": 5}, "reason": "x"})
