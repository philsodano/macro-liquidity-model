"""CLI: python -m macro refresh|build|report|all"""
from __future__ import annotations

import argparse
import sys
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="macro")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh", help="fetch due series")
    r.add_argument("--ids")
    r.add_argument("--force", action="store_true", help="ignore refresh cadence")
    r.set_defaults(func=cmd_refresh)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
