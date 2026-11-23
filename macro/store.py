"""CSV store with an append-only vintage log.

data/series/<id>.csv    current values (obs_date,value)
data/vintages/<id>.csv  every value ever seen (obs_date,value,seen_at,origin)
data/meta/<id>.json     fetch metadata
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .registry import ROOT


class Store:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else ROOT
        for sub in ("series", "vintages", "meta"):
            (self.root / "data" / sub).mkdir(parents=True, exist_ok=True)

    def _p(self, kind: str, sid: str, ext: str = "csv") -> Path:
        return self.root / "data" / kind / f"{sid}.{ext}"

    def ids(self) -> list[str]:
        return sorted(p.stem for p in (self.root / "data" / "series").glob("*.csv"))

    def write(self, sid: str, s: pd.Series, seen_at: date, origin: str = "fetch") -> int:
        """Merge observations; log new or changed values. Returns count of new/changed obs."""
        if s is None or s.empty:
            return 0
        s = pd.Series(s, dtype=float).dropna()
        s.index = pd.to_datetime(s.index).normalize()
        s = s[~s.index.duplicated(keep="last")].sort_index()
        cur = self.read(sid)
        joined = s.to_frame("new").join(cur.rename("old"), how="left")
        changed = joined[joined["old"].isna() | ~np.isclose(joined["new"], joined["old"], rtol=1e-12, atol=1e-12)]
        if changed.empty:
            return 0
        merged = pd.concat([cur[~cur.index.isin(changed.index)], changed["new"]]).sort_index()
        out = pd.DataFrame({"obs_date": merged.index.strftime("%Y-%m-%d"), "value": merged.values})
        out.to_csv(self._p("series", sid), index=False)
        vint = pd.DataFrame({
            "obs_date": changed.index.strftime("%Y-%m-%d"),
            "value": changed["new"].values,
            "seen_at": pd.Timestamp(seen_at).strftime("%Y-%m-%d"),
            "origin": origin,
        })
        vp = self._p("vintages", sid)
        vint.to_csv(vp, mode="a", header=not vp.exists(), index=False)
        return len(changed)

    def read(self, sid: str, as_of: date | None = None) -> pd.Series:
        if as_of is not None:
            vp = self._p("vintages", sid)
            if not vp.exists():
                return pd.Series(dtype=float, name=sid)
            v = pd.read_csv(vp)
            v = v[pd.to_datetime(v["seen_at"]) <= pd.Timestamp(as_of)]
            v = v[pd.to_datetime(v["obs_date"]) <= pd.Timestamp(as_of)]
            v = v.drop_duplicates("obs_date", keep="last")
            s = pd.Series(v["value"].astype(float).values, index=pd.to_datetime(v["obs_date"]), name=sid)
            return s.sort_index()
        p = self._p("series", sid)
        if not p.exists():
            return pd.Series(dtype=float, name=sid)
        df = pd.read_csv(p)
        return pd.Series(df["value"].astype(float).values, index=pd.to_datetime(df["obs_date"]), name=sid)

    def first_seen(self, sid: str) -> pd.Series:
        """Date each observation was first seen (release proxy)."""
        vp = self._p("vintages", sid)
        if not vp.exists():
            return pd.Series(dtype="datetime64[ns]")
        v = pd.read_csv(vp)
        g = v.groupby("obs_date")["seen_at"].min()
        return pd.Series(pd.to_datetime(g.values), index=pd.to_datetime(g.index))

    def meta(self, sid: str) -> dict:
        p = self._p("meta", sid, "json")
        return json.loads(p.read_text()) if p.exists() else {}

    def set_meta(self, sid: str, **kv) -> None:
        m = self.meta(sid)
        m.update(kv)
        self._p("meta", sid, "json").write_text(json.dumps(m, indent=1, default=str, sort_keys=True))
