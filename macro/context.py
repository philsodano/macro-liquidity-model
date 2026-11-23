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

    def s(self, sid: str) -> pd.Series:
        """Series as known at the run date (vintage-aware in as-of mode)."""
        if sid in self.extra_series:
            return self.extra_series[sid]
        if sid not in self._cache:
            s = self.store.read(sid, as_of=self.as_of)
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
            grace = self.settings.get("freshness_grace_days")
            self._sum[sid] = summarize(ind, self.s(sid), self.today, first_seen=fs, grace=grace)
        return self._sum[sid]

    def has(self, sid: str) -> bool:
        return not self.s(sid).empty
