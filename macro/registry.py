"""Indicator registry: one definition per series, loaded from config/indicators.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FREQS = {"D", "W", "M", "Q"}
SOURCES = {"fred", "treasury", "nyfed", "ecb", "boe", "bis", "sec", "tiingo", "files", "derived", "cftc", "ofr", "nyfedpd", "finra"}
SIGNALS = {"leading", "coincident", "lagging"}
PILLARS = {"central_bank", "fiscal", "banking", "private_credit", "global", "ai_capex"}


@dataclass(frozen=True)
class Indicator:
    id: str
    name: str
    source: str
    source_id: str
    units: str
    freq: str
    section: str
    signal: str
    polarity: int
    release_lag_days: int
    what: str = ""
    why: str = ""
    short: str = ""          # one-line plain-English label for the dashboard
    pillar: str | None = None
    role: str | None = None  # 'core' | 'member' | None
    display_only: bool = False
    transform: str = "level"  # level | yoy | diff
    scale: float = 1.0
    kind: str = "fact"        # fact | estimate
    params: dict = field(default_factory=dict)
    unavailable: str | None = None


_FIELDS = {f.name for f in fields(Indicator)}


def load_registry(path: Path | None = None) -> dict[str, Indicator]:
    path = path or ROOT / "config" / "indicators.yaml"
    raw = yaml.safe_load(Path(path).read_text()) or []
    if isinstance(raw, dict):  # {defaults: ..., indicators: [...]} layout (defaults are YAML anchors)
        raw = raw.get("indicators", [])
    reg: dict[str, Indicator] = {}
    core_owner: dict[tuple[str, str], str] = {}
    for item in raw:
        item = dict(item)
        item.setdefault("source_id", item.get("id"))
        unknown = set(item) - _FIELDS
        if unknown:
            raise ValueError(f"{item.get('id')}: unknown keys {sorted(unknown)}")
        ind = Indicator(**item)
        if ind.id in reg:
            raise ValueError(f"duplicate id {ind.id}")
        if ind.freq not in FREQS:
            raise ValueError(f"{ind.id}: bad freq {ind.freq}")
        if ind.source not in SOURCES:
            raise ValueError(f"{ind.id}: unknown source {ind.source}")
        if ind.signal not in SIGNALS:
            raise ValueError(f"{ind.id}: bad signal {ind.signal}")
        if ind.pillar is not None and ind.pillar not in PILLARS:
            raise ValueError(f"{ind.id}: unknown pillar {ind.pillar}")
        if ind.role == "core":
            key = (ind.source, ind.source_id)
            if key in core_owner and core_owner[key] != ind.pillar:
                raise ValueError(f"{ind.id}: {key} is core in two pillars ({core_owner[key]}, {ind.pillar})")
            core_owner[key] = ind.pillar
        reg[ind.id] = ind
    return reg


def load_settings(path: Path | None = None) -> dict:
    path = path or ROOT / "config" / "settings.yaml"
    return yaml.safe_load(Path(path).read_text()) or {}
