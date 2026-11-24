"""Weekly research report: built from the same snapshot as the dashboard, so the numbers always match.

Analyst notes (notes/YYYY-MM-DD.md, '## <Section name>' headings) are inserted under the matching section and
labelled as interpretation. Output: reports/YYYY-MM-DD.md (+ .json with HTML for the dashboard)."""
from __future__ import annotations

import html as H
import json
import re
from datetime import date, timedelta
from pathlib import Path

from ..freshness import expected_next_release
from ..registry import ROOT, load_registry, load_settings

SECTIONS = ["Executive Summary", "Liquidity Update", "Central Banks", "Consumer and Employment", "Economic Cycle",
            "Financial Markets", "Investment Implications", "Forward Outlook"]
CATALYST_IDS = {"PAYEMS": "Jobs report", "CPIAUCSL": "CPI", "PCEPILFE": "PCE inflation", "GDPC1": "GDP",
                "RSAFS": "Retail sales", "JTSJOL": "Job openings (JOLTS)", "DRTSCILM": "Senior Loan Officer Survey",
                "WALCL": "Fed balance sheet (H.4.1)", "ICSA": "Jobless claims"}


def _f(x, fmt="{:+.2f}"):
    return "n/a" if x is None else fmt.format(x)


def parse_notes(md: str | None) -> dict[str, str]:
    if not md:
        return {}
    out, cur = {}, None
    for line in md.splitlines():
        m = re.match(r"^##\s+(?:\d+\.\s*)?(.+?)\s*$", line)
        if m:
            cur = m.group(1).strip().lower()
            out[cur] = ""
        elif cur is not None:
            out[cur] += line + "\n"
    return {k: v.strip() for k, v in out.items() if v.strip()}


def catalysts(snap: dict, root: Path) -> list[str]:
    reg = load_registry()
    today = date.fromisoformat(snap["meta"]["as_of"])
    rows = {r["id"]: r for r in snap["data_quality"]["rows"]}
    out = []
    fomc = [date.fromisoformat(d) for d in load_settings().get("fomc_decisions", [])]
    nxt = [d for d in fomc if d >= today]
    if nxt:
        out.append(f"FOMC decision {nxt[0].isoformat()} (Fed calendar; verify on federalreserve.gov).")
    items = []
    for sid, label in CATALYST_IDS.items():
        r = rows.get(sid)
        if not r or not r.get("obs_date") or sid not in reg:
            continue
        due = expected_next_release(reg[sid], date.fromisoformat(r["obs_date"]))
        if due <= today + timedelta(days=21):
            items.append((max(due, today), label, due < today))
    for d, label, late in sorted(items):
        out.append(f"{label}: {'due now (expected ' + d.isoformat() + ')' if late else 'expected around ' + d.isoformat()} — estimate from its usual release lag.")
    return out


def blocks(snap: dict, prev: dict | None, notes: dict[str, str], root: Path) -> list[tuple]:
    ex, sc, liq = snap["executive"], snap["scenarios"], snap["liquidity"]
    c = liq["consolidated"]
    f = sc["final"]
    changes = snap.get("changes", {}).get("items", [])
    sig = sorted([s for s in snap["signals"] if s.get("available", True)], key=lambda s: -abs(s["score"]))
    B: list[tuple] = [("h1", f"Weekly Macro & Liquidity Report — {snap['meta']['as_of']}")]
    B.append(("p", f"Data as of {snap['meta']['as_of']}; built {snap['meta']['built_at']}. Same data and model as the dashboard. "
                   "Facts are published data; anything marked estimate or interpretation is the model's or the analyst's read."))

    def section(i, name, body):
        B.append(("h2", f"{i}. {name}"))
        B.extend(body)
        n = notes.get(name.lower())
        if n:
            B.append(("h3", "Analyst interpretation"))
            B.append(("p", n))

    prev_txt = f" (from {', '.join(f'{k} {prev['scenarios']['final'][k]:.0f}%' for k in ('base', 'bull', 'bear'))})" \
        if prev and prev.get("scenarios") else ""
    body = [("p", " ".join(ex["thesis"][:2])),
            ("p", f"Scenario odds: base {f['base']:.0f}%, bull {f['bull']:.0f}%, bear {f['bear']:.0f}%{prev_txt}.")]
    if changes:
        body.append(("h3", f"What changed since {snap['changes'].get('previous_date')}"))
        body.append(("ul", [f"{x['field']}: {x['before']} → {x['after']}. {x.get('why', '')}".strip() for x in changes[:8]]))
    else:
        body.append(("p", "First report: this sets the baseline. Future reports lead with what changed."))
    body.append(("h3", "What matters most"))
    body.append(("ul", [f"{s['label']} ({'supportive' if s['score'] > 0 else 'headwind'}, {s['score']:+.1f}): {s['evidence']}" for s in sig[:3]]))
    section(1, SECTIONS[0], body)

    lines = [f"Market liquidity (Fed, global, credit): {_f(c['market']['composite'])} — {c['market']['state']}, {c['market']['trend']}.",
             f"Economy liquidity (deficits, banks, AI capex): {_f(c['economy']['composite'])} — {c['economy']['state']}, {c['economy']['trend']}.",
             f"All six pillars: {_f(c['composite'])}; {c['breadth']['adding']} adding, {c['breadth']['draining']} draining."]
    pills = [f"{p['title']}: {p['state']}, {p['trend']} (impulse {_f(p['impulse'])}). {p['drivers'][0]}" for p in liq["pillars"]]
    section(2, SECTIONS[1], [("ul", lines), ("ul", pills),
                             ("p", "Liquidity scores are z-scores of the change in each pillar (0 = normal). Pillars are combined as scores, never by adding dollar amounts.")])

    cb = snap["central_banks"]
    rows = [[r["bank"], f"{r['rate']:.2f}%", _f(r["change_12m"], "{:+.2f}pp"), r["obs_date"]] for r in cb["rates_table"]]
    section(3, SECTIONS[2], [("table", ["Central bank", "Rate", "12-month change", "As of"], rows),
                             ("ul", [s["evidence"] for s in cb["signals"] if s.get("available", True)] + cb["notes"])])

    con = snap["consumer"]
    section(4, SECTIONS[3], [("p", f"Funding of spending: {con['diagnosis']}. {con['diagnosis_text']}"),
                             ("ul", [s["evidence"] for s in con["labour_signals"]] + [s["evidence"] for s in con["consumer_signals"]]),
                             ("p", " ".join(con["implications"]))])

    cy = snap["cycle"]
    cl = cy["classification"]
    movers = sorted([x for x in cy["leading"] + cy["coincident"] if x.get("z") is not None], key=lambda x: -abs(x["z"]))[:4]
    section(5, SECTIONS[4], [("p", f"Cycle: {cy['label']}. Mix: {cl['quadrant']}. Leading indicators {_f(cl['leading'])}, current activity "
                                   f"{_f(cl['coincident'])} (z-scores). Yield-curve recession odds {_f(cy['recession_prob'], '{:.0f}%')} over 12 months."),
                             ("ul", [f"{m['label']}: {m['z']:+.2f}" for m in movers])])

    mk = snap["markets"]
    conf = [x["question"] for x in snap["cross_asset"] if x["verdict"] == "confirm"]
    div = [f"{x['question']} {x['meaning']}" for x in snap["cross_asset"] if x["verdict"] == "diverge"]
    comp = [f"{r['asset']}: {r['measure']} {r.get('display', r['value'])} — {r['verdict']}" for r in mk["compensation"] if r.get("value") is not None]
    pos = snap.get("positioning") or {}
    pos_lines = [("h3", "Positioning"), ("p", pos.get("summary") or "No positioning data.")]
    pos_lines += [("ul", [s["evidence"] for s in pos.get("signals", []) if s.get("available", True)])] if pos.get("signals") else []
    section(6, SECTIONS[5], [("ul", comp), ("p", f"Confirming: {len(conf)} checks. Diverging: {len(div)}."), ("ul", div or ["No cross-asset divergences flagged."]),
                             ("p", f"Risk appetite {_f(mk['readings'].get('risk_appetite'))}; curve {mk['curve_shape']}.")] + pos_lines)

    al = snap["allocation"]
    ranked = sorted(al["assets"], key=lambda a: -a["score"])
    sec_r = al["sectors"]
    section(7, SECTIONS[6], [("ul", [f"{a['asset']} — {a['stance']} ({a['score']:+.2f}). {a['why']} Market expects: {a['priced_in']} Invalidated if: {a['invalidation']}"
                                     for a in ranked[:3] + ranked[-3:]]),
                             ("p", "Sectors favoured: " + ", ".join(f"{s['asset']} ({s['score']:+.2f})" for s in sec_r[:3])
                              + ". Least favoured: " + ", ".join(f"{s['asset']} ({s['score']:+.2f})" for s in sec_r[-3:]) + "."),
                             ("p", "These are framework scores that explain the macro reasoning, not buy or sell recommendations.")])

    t = sc["text"]
    out = []
    for k in ("base", "bull", "bear"):
        out.append(("h3", f"{t[k]['name']} — {f[k]:.0f}%"))
        out.append(("ul", [t[k]["economy"], "Liquidity: " + t[k]["liquidity"], "Fed: " + t[k]["central_bank"], "Markets: " + t[k]["markets"],
                           "Watch for: " + "; ".join(t[k]["confirm"][:3]) + "."]))
    out.append(("h3", "Upcoming catalysts"))
    out.append(("ul", catalysts(snap, root) or ["No scheduled releases found in the next three weeks."]))
    section(8, SECTIONS[7], out)
    return B


def _md(B) -> str:
    out = []
    for b in B:
        k = b[0]
        if k == "h1":
            out.append(f"# {b[1]}\n")
        elif k == "h2":
            out.append(f"\n## {b[1]}\n")
        elif k == "h3":
            out.append(f"\n### {b[1]}\n")
        elif k == "p":
            out.append(b[1] + "\n")
        elif k == "ul":
            out.append("\n".join(f"- {x}" for x in b[1]) + "\n")
        elif k == "table":
            out.append("| " + " | ".join(b[1]) + " |\n|" + "---|" * len(b[1]) + "\n" + "\n".join("| " + " | ".join(map(str, r)) + " |" for r in b[2]) + "\n")
    return "\n".join(out)


def _html(B) -> str:
    e = H.escape
    out = []
    for b in B:
        k = b[0]
        if k in ("h1", "h2", "h3"):
            out.append(f"<{'h2' if k == 'h1' else k}>{e(b[1])}</{'h2' if k == 'h1' else k}>")
        elif k == "p":
            out.append("".join(f"<p>{e(par)}</p>" for par in b[1].split("\n\n")))
        elif k == "ul":
            out.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in b[1]) + "</ul>")
        elif k == "table":
            out.append('<div class="tbl-wrap"><table><thead><tr>' + "".join(f"<th>{e(h)}</th>" for h in b[1]) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in b[2]) + "</tbody></table></div>")
    return "\n".join(out)


def render_report(snap: dict, prev: dict | None, notes_md: str | None, root: Path | None = None) -> dict:
    root = Path(root) if root else ROOT
    B = blocks(snap, prev, parse_notes(notes_md), root)
    return {"date": snap["meta"]["as_of"], "title": B[0][1], "md": _md(B), "html": _html(B)}


def write_report(rep: dict, root: Path | None = None) -> Path:
    d = (Path(root) if root else ROOT) / "reports"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{rep['date']}.md").write_text(rep["md"])
    (d / f"{rep['date']}.json").write_text(json.dumps({k: rep[k] for k in ("date", "title", "html")}))
    return d / f"{rep['date']}.md"


def load_reports(root: Path | None = None) -> list[dict]:
    d = (Path(root) if root else ROOT) / "reports"
    out = []
    for p in sorted(d.glob("*.json"), reverse=True):
        try:
            out.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    return out
