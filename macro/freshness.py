"""Is the latest observation as recent as the release calendar says it should be?"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

PERIOD = {"D": pd.DateOffset(days=1), "W": pd.DateOffset(weeks=1), "M": pd.DateOffset(months=1),
          "Q": pd.DateOffset(months=3)}
DEFAULT_GRACE = {"D": 5, "W": 10, "M": 25, "Q": 45}


def expected_next_release(ind, last_obs: date) -> date:
    return (pd.Timestamp(last_obs) + PERIOD[ind.freq] + timedelta(days=ind.release_lag_days)).date()


def freshness(ind, last_obs: date | None, today: date, grace: dict | None = None) -> str:
    """fresh: next release not yet due · due: release expected/late within grace · stale: beyond grace."""
    if last_obs is None:
        return "missing"
    g = (grace or DEFAULT_GRACE)[ind.freq]
    nxt = expected_next_release(ind, last_obs)
    if today < nxt:
        return "fresh"
    if today <= nxt + timedelta(days=g):
        return "due"
    return "stale"
