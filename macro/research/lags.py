"""Transmission lags: how long before a driver shows up in its target, with bootstrap uncertainty."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..transforms import yoy


def _monthly(s: pd.Series, how: str = "mean") -> pd.Series:
    s = s.dropna()
    if s.empty:
        return s
    r = s.resample("MS")
    return (r.mean() if how == "mean" else r.last()).dropna()


def lead_lag(x: pd.Series, y: pd.Series, max_lag: int = 24, n_boot: int = 500, block: int = 6, seed: int = 0,
             expected_sign: int | None = None) -> dict:
    """corr(x_t, y_{t+k}) for k = 0..max_lag. Best lag = largest |corr|, or — when the economic sign is known —
    the largest correlation with that sign (so a same-month policy *reaction* is not mistaken for the effect).
    CI = 5–95% of the best lag under a moving-block bootstrap (keeps autocorrelation). Monthly inputs."""
    df = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    if len(df) < max_lag + 36:
        return {"best_lag": None, "corr": None, "ci": (None, None), "n": len(df), "all_lags": {}}
    xs, ys = df["x"].values, df["y"].values
    n = len(xs) - max_lag

    def corrs(ix):
        out = []
        for k in range(max_lag + 1):
            a, b = xs[ix], ys[ix + k]
            out.append(np.corrcoef(a, b)[0, 1] if a.std() > 0 and b.std() > 0 else 0.0)
        return np.array(out)

    pick = (lambda c: int(np.nanargmax(np.abs(c)))) if expected_sign is None else \
        (lambda c: int(np.nanargmax(c * expected_sign)))
    base = corrs(np.arange(n))
    best = pick(base)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    boots = []
    for _ in range(n_boot):
        starts = rng.integers(0, n - block + 1, nb)
        ix = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        boots.append(pick(corrs(ix)))
    lo, hi = np.percentile(boots, [5, 95])
    return {"best_lag": best, "corr": round(float(base[best]), 3), "ci": (int(lo), int(hi)), "n": int(n),
            "all_lags": {int(k): round(float(v), 3) for k, v in enumerate(base)}}


def _pairs(ctx) -> list[tuple]:
    s, has, ex = ctx.s, ctx.has, ctx.extra_series
    out = []
    if has("DFF") and has("UNRATE"):
        out.append(("Interest rates → unemployment", "Fed funds, 12m change", "Unemployment, 12m change",
                    _monthly(s("DFF")).diff(12), _monthly(s("UNRATE")).diff(12), 36, "+"))
    if "BANK_CREDIT_IMPULSE" in ex and has("GDPC1"):
        out.append(("Bank credit → GDP", "Bank credit impulse", "Real GDP, y/y",
                    _monthly(ex["BANK_CREDIT_IMPULSE"]), _monthly(yoy(s("GDPC1")), "last").resample("MS").ffill(), 24, "+"))
    if has("DRTSCILM") and has("TOTCI"):
        out.append(("Lending standards → business loans", "Banks tightening (net %)", "C&I loans, y/y",
                    _monthly(s("DRTSCILM"), "last").resample("MS").ffill(), _monthly(yoy(s("TOTCI"))), 24, "−"))
    if "FISCAL_IMPULSE" in ex and has("PCEC96"):
        out.append(("Fiscal spending → consumption", "Fiscal impulse", "Real spending, y/y",
                    _monthly(ex["FISCAL_IMPULSE"]), _monthly(yoy(s("PCEC96"))), 24, "+"))
    if has("DEBT_COUPONS") and has("ACMTP10") and has("GDP"):
        c = _monthly(s("DEBT_COUPONS").add(s("DEBT_BONDS"), fill_value=0), "last")
        g = _monthly(s("GDP"), "last").resample("MS").ffill().reindex(c.index).ffill()
        out.append(("Treasury coupon supply → term premium", "Net coupon issuance, 12m, % GDP", "Term premium, 12m change",
                    (c.diff(12) / g * 100), _monthly(s("ACMTP10")).diff(12), 24, "+"))
    if has("TOTALSL") and has("RRSFS"):
        out.append(("Consumer borrowing → retail sales", "Consumer credit, y/y", "Real retail sales, y/y",
                    _monthly(yoy(s("TOTALSL"))), _monthly(yoy(s("RRSFS"))), 18, "+"))
    if has("NEWORDER") and has("PNFIC1"):
        out.append(("Capex orders → business investment", "Core capital goods orders, y/y", "Real business investment, y/y",
                    _monthly(yoy(s("NEWORDER"))), _monthly(yoy(s("PNFIC1")), "last").resample("MS").ffill(), 18, "+"))
    if "NETLIQ" in ex and "SPX_LONG" in ex:
        nl = _monthly(ex["NETLIQ"], "last")
        out.append(("Fed liquidity → stocks", "Net liquidity, 3m % change", "S&P 500, next 3m return",
                    nl.pct_change(3, fill_method=None) * 100, ex["SPX_LONG"].pct_change(3, fill_method=None) * 100, 12, "+"))
    if has("BAA10Y") and has("PAYEMS"):
        out.append(("Credit spreads → jobs", "Baa spread, 6m change", "Payrolls, y/y",
                    _monthly(s("BAA10Y")).diff(6), _monthly(yoy(s("PAYEMS"))), 24, "−"))
    return out


def estimate_lags(ctx, n_boot: int = 300) -> list[dict]:
    rows = []
    for name, xl, yl, x, y, max_lag, expect in _pairs(ctx):
        x = x[x.index >= "1985-01-01"]
        r = lead_lag(x, y, max_lag=max_lag, n_boot=n_boot, expected_sign=1 if expect == "+" else -1)
        sign_ok = r["corr"] is not None and ((r["corr"] > 0) == (expect == "+"))
        width = None if r["best_lag"] is None else r["ci"][1] - r["ci"][0]
        rows.append({"channel": name, "driver": xl, "target": yl, "best_lag_months": r["best_lag"], "corr": r["corr"],
                     "ci_months": list(r["ci"]), "n": r["n"], "expected_sign": expect, "sign_as_expected": sign_ok,
                     "confidence": "n/a" if width is None else "high" if width <= 4 and abs(r["corr"]) > .4
                     else "medium" if width <= 10 else "low", "profile": r["all_lags"]})
    return rows
