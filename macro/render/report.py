"""Weekly report rendering (Task 10 fills this in). load_reports() feeds the dashboard's Reports tab."""
from __future__ import annotations

import json
from pathlib import Path

from ..registry import ROOT


def load_reports(root: Path | None = None) -> list[dict]:
    d = (Path(root) if root else ROOT) / "reports"
    out = []
    for p in sorted(d.glob("*.json"), reverse=True):
        try:
            out.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    return out
