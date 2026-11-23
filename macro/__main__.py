"""CLI: python -m macro refresh|build|report|all"""
from __future__ import annotations

import argparse
import sys
import warnings
from datetime import date

from .registry import load_registry, load_settings
from .store import Store


def cmd_refresh(args) -> int:
    store, reg, settings = Store(), load_registry(), load_settings()
    ids = args.ids.split(",") if args.ids else None
    rep = __import__("macro.refresh", fromlist=["refresh"]).refresh(
        store, reg, settings, today=date.today(), only_due=not args.force, ids=ids,
        log=lambda sid, r: print(f"{r['status']:>9}  {sid:<22} +{r['new_obs']:<6} {r['error'] or ''}", flush=True))
    failed = [k for k, v in rep.items() if v["status"] == "failed"]
    print(f"\n{len(rep)} series: {sum(v['status'] == 'updated' for v in rep.values())} updated, {len(failed)} failed")
    return 0


def cmd_build(args) -> int:
    from .snapshot import build_snapshot
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    snap = build_snapshot(Store(), load_registry(), load_settings(), today=date.today(), as_of=as_of,
                          research=not args.no_research, write=not as_of)
    q = snap["data_quality"]["counts"]
    sc = snap["scenarios"]["final"]
    print(f"snapshot {snap['meta']['as_of']} ({snap['meta']['mode']}): base {sc['base']}% / bull {sc['bull']}% / "
          f"bear {sc['bear']}% · data {q} · {len(snap['changes']['items'])} changes vs {snap['changes']['previous_date']}")
    if not as_of:
        from .render.dashboard import render_dashboard
        from .render.report import load_reports
        out = render_dashboard(snap, load_reports())
        print(f"dashboard written: {out}")
    return 0


def cmd_all(args) -> int:
    args.ids, args.force = None, False
    cmd_refresh(args)
    args.as_of, args.no_research = None, False
    return cmd_build(args)


def main(argv=None) -> int:
    warnings.filterwarnings("ignore", message=".*Sorting by default when concatenating.*")
    ap = argparse.ArgumentParser(prog="macro")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh", help="fetch due series")
    r.add_argument("--ids")
    r.add_argument("--force", action="store_true", help="ignore refresh cadence")
    r.set_defaults(func=cmd_refresh)
    b = sub.add_parser("build", help="run the model and write site/snapshot.json")
    b.add_argument("--as-of", help="point-in-time run, YYYY-MM-DD (not saved to history)")
    b.add_argument("--no-research", action="store_true", help="skip lags/analogues/back-tests (faster)")
    b.set_defaults(func=cmd_build)
    a = sub.add_parser("all", help="refresh due data, then build")
    a.set_defaults(func=cmd_all)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
