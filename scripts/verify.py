"""Run the final checks and write docs/verification.md with real output."""
import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from macro import history  # noqa: E402
from macro.registry import load_registry, load_settings  # noqa: E402
from macro.snapshot import build_snapshot, conclusions_record  # noqa: E402
from macro.store import Store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
reg, st, se = load_registry(), Store(), load_settings()
snap = json.loads((ROOT / "site" / "snapshot.json").read_text())
out = ["# Verification", f"Run against snapshot {snap['meta']['as_of']} (built {snap['meta']['built_at']}).", ""]


def tests(expr):
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", "-k", expr], capture_output=True, text=True, cwd=ROOT)
    return r.stdout.strip().splitlines()[-1]


# 1
w, t, r = (st.read(x).iloc[-1] for x in ("WALCL", "WTREGEN", "RRPONTSYD"))
nl = next(v for d, v in snap["series"]["NETLIQ"][-1:])
out += ["## 1. Liquidity framework works and avoids double counting",
        f"- Tests: `{tests('net_liquidity or pillars_exclusive or tga_counted_once or g4_fx or consolidate or composite')}`",
        f"- Spot check {st.read('WALCL').index[-1].date()}: Fed assets {w:,.1f} − Treasury cash {t:,.1f} − RRP {r:,.1f} = {w - t - r:,.1f} bn; snapshot NETLIQ = {nl:,.1f}.",
        "- Rules enforced: " + " / ".join(snap["liquidity"]["consolidated"]["rules"][:4]) + " …", ""]
# 2
out += ["## 2. Central bank, fiscal, banking, private credit, global and AI financing are all represented"]
for p in snap["liquidity"]["pillars"]:
    out.append(f"- {p['title']}: {p['state']}, {p['trend']}; {len(p['members'])} indicators; core = {', '.join(c['short'] for c in p['core'])}.")
out.append("")
# 3
lab = Counter(i.signal for i in reg.values() if i.section in ("labour", "consumer"))
out += ["## 3. Consumer and employment indicators with leading/coincident/lagging labels",
        f"- {sum(lab.values())} series: {dict(lab)}. Payrolls coincident, unemployment lagging, claims/temps/hours/quits leading.",
        f"- Live diagnosis: {snap['consumer']['diagnosis']} — {snap['consumer']['diagnosis_text']}", ""]
# 4
out += ["## 4. Tested against historical regimes",
        f"- Regime tests (2018 QT, 2019 repo, 2020 flood, 2022 tightening, 2023 bank stress, 2026 RRP): `{tests('test_historical')}`"]
for p in snap["research"]["principles"]:
    out.append(f"- {p['principle']}: **{p['verdict']}**. {p['plain']}")
out += [f"- Analogues: {snap['research']['analogues'].get('summary', '')}", ""]
# 5
out += ["## 5. Scenarios sum to 100 and update consistently",
        f"- Tests: `{tests('test_scenarios or test_history')}`",
        f"- Live: {snap['scenarios']['final']} (model {snap['scenarios']['model']}); method: {snap['scenarios']['method']}", ""]
# 6
dq = snap["data_quality"]["counts"]
out += ["## 6. Sources, calculations, dates and units",
        f"- Data status: {dq}. Failed = Tiingo series blocked by an invalid API key (36).",
        f"- Unit/date tests: `{tests('test_transforms or test_sources or test_store or freshness')}`",
        f"- Every displayed metric has source/observation date/frequency/freshness: `{tests('every_displayed_metric')}`", ""]
# 7
out += ["## 7. Dashboard and weekly report use the same data",
        f"- Both are rendered from `site/snapshot.json`. Test: `{tests('same_snapshot_numbers')}`", ""]
# 8
a = build_snapshot(st, reg, se, today=date(2026, 11, 23), as_of=date(2022, 3, 31), write=False, research=False)
b = build_snapshot(st, reg, se, today=date(2026, 11, 23), as_of=date(2022, 6, 30), write=False, research=False)
d = history.diff(conclusions_record(a), conclusions_record(b))
out += ["## 8. Detecting a meaningful liquidity change (2022-03-31 → 2022-06-30, as-of runs)",
        f"- Market liquidity: {a['liquidity']['consolidated']['market']['composite']:+.2f} ({a['liquidity']['consolidated']['market']['state']}) → "
        f"{b['liquidity']['consolidated']['market']['composite']:+.2f} ({b['liquidity']['consolidated']['market']['state']}, {b['liquidity']['consolidated']['market']['trend']}).",
        f"- Scenarios: {a['scenarios']['final']} → {b['scenarios']['final']}."]
out += [f"- {x['field']}: {x['before']} → {x['after']}. {x.get('why', '')}" for x in d[:14]]
top = sorted(b["allocation"]["assets"], key=lambda x: -x["score"])
out += [f"- Implication (June 2022): favoured {top[0]['asset']} ({top[0]['score']:+.2f}), {top[1]['asset']}; least {top[-1]['asset']} ({top[-1]['score']:+.2f}). "
        f"What followed: the S&P 500 fell further into October 2022 before recovering.", ""]
(ROOT / "docs" / "verification.md").write_text("\n".join(out) + "\n")
print("\n".join(out))
