"""Run context: point-in-time data access, cached summaries, and derived series for charts."""
from __future__ import annotations

from datetime import date

import pandas as pd

from .transforms import summarize


class Ctx:
    def __init__(self, store, registry, today: date, as_of: date | None = None, settings: dict | None = None):
        self.store, self.registry, self.settings = store, registry, settings or {}
        self.as_of = as_of
        self.today = as_of or today
        self.extra_series: dict[str, pd.Series] = {}
        self._cache: dict[str, pd.Series] = {}
        self._sum: dict[str, dict] = {}
        self.pseudo_pit: set[str] = set()   # series reconstructed from today's vintage (no older vintage on file)

    def s(self, sid: str) -> pd.Series:
        """Series as known at the run date (vintage-aware in as-of mode)."""
        if sid in self.extra_series:
            return self.extra_series[sid]
        if sid not in self._cache:
            s = self.store.read(sid, as_of=self.as_of)
            if s.empty and self.as_of is not None:
                # No vintage that old in our log: use today's vintage, keeping only observations that would have
                # been published by then (obs date + typical release lag). Revisions since then are NOT undone.
                full = self.store.read(sid)
                if not full.empty:
                    lag = self.registry[sid].release_lag_days if sid in self.registry else 0
                    s = full[full.index + pd.Timedelta(days=lag) <= pd.Timestamp(self.as_of)]
                    self.pseudo_pit.add(sid)
            if not s.empty:
                s = s[s.index <= pd.Timestamp(self.today)]
            self._cache[sid] = s
        return self._cache[sid]

    def put(self, key: str, s: pd.Series) -> pd.Series:
        s = s.dropna().sort_index()
        self.extra_series[key] = s
        self._sum.pop(key, None)
        return s

    def summary(self, sid: str) -> dict:
        if sid not in self._sum:
            ind = self.registry[sid]
            fs = None if ind.source == "derived" else self.store.first_seen(sid)
            if fs is not None and self.as_of is not None:
                fs = fs[fs <= pd.Timestamp(self.as_of)]
            grace = self.settings.get("freshness_grace_days")
            summ = summarize(ind, self.s(sid), self.today, first_seen=fs, grace=grace)
            inputs = [i for i in (ind.params or {}).get("inputs", []) if i in self.registry]
            if ind.source == "derived" and inputs and summ["latest"] is not None:
                # a model series is as fresh as its stalest input (its own date can lag the inputs' release)
                rank = {"fresh": 0, "due": 1, "stale": 2, "missing": 3}
                worst = max((self.summary(i)["freshness"] for i in inputs), key=lambda f: rank.get(f, 0))
                summ["freshness"] = worst if worst in rank else summ["freshness"]
                summ["inputs"] = inputs
            self._sum[sid] = summ
        return self._sum[sid]

    def has(self, sid: str) -> bool:
        return not self.s(sid).empty
