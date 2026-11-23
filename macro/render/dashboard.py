"""Write the static dashboard: site/index.html (template) + snapshot.json + reports.json beside it."""
from __future__ import annotations

import json
from pathlib import Path

from ..registry import ROOT

TEMPLATE = Path(__file__).parent / "templates" / "dashboard.html"
# Letters follow the research spec's section order (A–H); the last three are supporting pages.
TABS = [("overview", "Overview"), ("central-banks", "Central banks"), ("liquidity", "Liquidity engine"),
        ("consumer", "Consumer & jobs"), ("cycle", "Business cycle"), ("inflation", "Inflation"),
        ("markets", "Markets & risk"), ("outlook", "Outlook"), ("research", "Research"),
        ("reports", "Weekly reports"), ("data", "Data & methods")]


def render_dashboard(snapshot: dict, reports: list[dict], out_dir: Path | None = None) -> Path:
    out_dir = Path(out_dir) if out_dir else ROOT / "site"
    out_dir.mkdir(parents=True, exist_ok=True)
    nav = "".join(f'<a href="#{tid}"><span class="k">{"ABCDEFGH"[i] if i < 8 else "·"}</span>{label}</a>'
                  for i, (tid, label) in enumerate(TABS))
    html = TEMPLATE.read_text().replace("<!--NAV-->", nav).replace("/*TABS*/[]", json.dumps(TABS))
    html = html.replace("<title>Liquidity Cycle Monitor</title>", '<title>Liquidity Cycle Monitor</title>\n<meta charset="utf-8">', 1)
    out = out_dir / "index.html"
    out.write_text(html)
    (out_dir / "snapshot.json").write_text(json.dumps(snapshot, separators=(",", ":")))
    (out_dir / "reports.json").write_text(json.dumps(reports, separators=(",", ":")))
    return out
