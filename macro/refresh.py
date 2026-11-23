"""Fetch due series into the store. One failing source never stops the run or erases history."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from .sources import SOURCES


def _due(store, ind, settings, today: date) -> bool:
    every = settings.get("refresh_days", {}).get(ind.source, 1)
    last = store.meta(ind.id).get("last_fetch")
    return last is None or (today - date.fromisoformat(last)).days >= every


def refresh(store, registry, settings, today: date, only_due: bool = True, ids: list[str] | None = None,
            log=None) -> dict:
    report: dict[str, dict] = {}
    start = settings.get("history_start", "1985-01-01")
    for sid, ind in registry.items():
        if ids and sid not in ids:
            continue
        if ind.source == "derived" or ind.unavailable:
            report[sid] = {"status": "skipped", "new_obs": 0, "error": ind.unavailable}
            continue
        if only_due and not _due(store, ind, settings, today):
            report[sid] = {"status": "skipped", "new_obs": 0, "error": None}
            continue
        try:
            s = SOURCES[ind.source](ind, pd.Timestamp(start).date())
            n = store.write(sid, s, seen_at=today)
            store.set_meta(sid, last_fetch=today.isoformat(), last_error=None, source=ind.source,
                           fetched_at=datetime.now().isoformat(timespec="seconds"))
            report[sid] = {"status": "updated" if n else "unchanged", "new_obs": n, "error": None}
        except Exception as e:  # noqa: BLE001 - record and continue
            store.set_meta(sid, last_error=f"{type(e).__name__}: {e}"[:300], last_error_at=today.isoformat())
            report[sid] = {"status": "failed", "new_obs": 0, "error": str(e)[:300]}
        if log:
            log(sid, report[sid])
    return report
