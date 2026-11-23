"""Research layer: analogues (also builds the long S&P series), transmission lags, principle tests."""
from __future__ import annotations

from . import analogues, backtest, lags


def assess(ctx, n_boot: int = 300) -> dict:
    an = analogues.assess(ctx)           # must run first: builds SPX_LONG
    return {"analogues": an, "lags": lags.estimate_lags(ctx, n_boot=n_boot), "principles": backtest.principle_tests(ctx)}
