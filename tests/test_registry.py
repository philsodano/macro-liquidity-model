from pathlib import Path

import pytest

from macro.registry import load_registry, load_settings

BASE = """
- id: A
  name: Series A
  source: fred
  source_id: A
  units: USD bn
  freq: W
  section: liquidity
  pillar: central_bank
  role: core
  signal: leading
  polarity: 1
  release_lag_days: 1
  what: a
  why: b
"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "ind.yaml"
    p.write_text(text)
    return p


def test_load_registry_defaults(tmp_path):
    reg = load_registry(_write(tmp_path, BASE))
    a = reg["A"]
    assert a.freq == "W" and a.scale == 1.0 and a.kind == "fact" and a.display_only is False


def test_load_registry_rejects_duplicate_id(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        load_registry(_write(tmp_path, BASE + BASE))


def test_load_registry_rejects_duplicate_core(tmp_path):
    # same underlying series (fred/A) registered as core in a second pillar
    second = BASE.replace("- id: A", "- id: B").replace("pillar: central_bank", "pillar: fiscal")
    with pytest.raises(ValueError, match="core"):
        load_registry(_write(tmp_path, BASE + second))


def test_load_registry_rejects_bad_freq(tmp_path):
    with pytest.raises(ValueError, match="freq"):
        load_registry(_write(tmp_path, BASE.replace("freq: W", "freq: X")))


def test_real_config_loads():
    reg = load_registry()
    assert len(reg) > 0
    assert isinstance(load_settings(), dict)
