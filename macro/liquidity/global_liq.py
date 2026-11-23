"""Pillar 5 — Global: foreign central-bank balance sheets in dollars, the dollar, dollar funding."""
from __future__ import annotations

import pandas as pd

from .central_bank import asof_align
from .common import build_pillar, fmt_bn, fmt_level


def balance_sheets_usd(books: dict[str, tuple[pd.Series, pd.Series]], horizon_weeks: int = 13) -> pd.DataFrame:
    """books: name -> (local-currency assets, USD per unit of local currency), already on a common index.

    ΔUSD = Σ ΔL·X(t−h)  [local balance-sheet growth]  +  Σ L(t)·ΔX  [currency translation] — sums exactly.
    """
    cols = {}
    for name, (loc, fx) in books.items():
        df = pd.concat([loc.rename("L"), fx.rename("X")], axis=1).dropna()
        cols[name] = df
    idx = sorted(set.intersection(*[set(d.index) for d in cols.values()]))
    out = pd.DataFrame(index=pd.DatetimeIndex(idx))
    local = fxc = total = 0
    for name, df in cols.items():
        df = df.reindex(out.index)
        usd = df["L"] * df["X"]
        out[f"{name}_usd"] = usd
        total = total + usd
        local = local + (df["L"] - df["L"].shift(horizon_weeks)) * df["X"].shift(horizon_weeks)
        fxc = fxc + df["L"] * (df["X"] - df["X"].shift(horizon_weeks))
    out["usd_total"] = total
    out["usd_change"] = total - total.shift(horizon_weeks)
    out["local_contrib"] = local
    out["fx_contrib"] = fxc
    return out


def assess(ctx) -> dict:
    drivers, extra = [], {}
    if all(ctx.has(s) for s in ("ECBASSETSW", "JPNASSETS", "DEXUSEU", "DEXJPUS")):
        start = max(ctx.s("ECBASSETSW").index[0], ctx.s("JPNASSETS").index[0])
        idx = pd.date_range(start, pd.Timestamp(ctx.today), freq="W-WED")
        ecb = asof_align(ctx.s("ECBASSETSW"), idx, 10)
        boj = asof_align(ctx.s("JPNASSETS") * 1000, idx, 45)           # JPY tn → JPY bn
        eur = asof_align(ctx.s("DEXUSEU"), idx, 7)
        jpy = 1 / asof_align(ctx.s("DEXJPUS"), idx, 7)                  # USD per JPY
        bs = balance_sheets_usd({"ECB": (ecb, eur), "BOJ": (boj, jpy)}).dropna(subset=["usd_total"])
        if not bs.empty:
            ctx.put("G2_CB_USD", bs["usd_total"])
            ctx.put("G2_LOCAL_CONTRIB", bs["local_contrib"])
            ctx.put("G2_FX_CONTRIB", bs["fx_contrib"])
            last = bs.dropna().iloc[-1]
            extra["g2_decomposition"] = {k: round(float(last[k]), 1) for k in ("usd_change", "local_contrib", "fx_contrib")}
            drivers.append(f"ECB + BoJ balance sheets {fmt_level(last['usd_total'])} in dollars; 13-week change "
                           f"{fmt_bn(last['usd_change'])} = balance sheets {fmt_bn(last['local_contrib'])} "
                           f"+ currency moves {fmt_bn(last['fx_contrib'])}.")
            if ctx.has("WALCL"):
                fed = asof_align(ctx.s("WALCL"), bs.index, 7)
                ctx.put("G3_CB_USD", (bs["usd_total"] + fed).dropna())
    if ctx.has("DTWEXBGS"):
        s = ctx.summary("DTWEXBGS")
        p = s["pct_changes"].get("13w")
        if p is not None:
            drivers.append(f"Dollar {p:+.1f}% over 13 weeks ({'tighter' if p > 0 else 'easier'} global dollar conditions).")
    if ctx.has("SWPT") and ctx.s("SWPT").iloc[-1] > 5:
        drivers.append(f"Fed swap lines in use: {fmt_level(ctx.s('SWPT').iloc[-1])} — a sign of offshore dollar stress.")
    if ctx.has("WMTSECL1"):
        s = ctx.summary("WMTSECL1")
        ch = s["changes"].get("13w")
        if ch is not None:
            drivers.append(f"Foreign central banks' Treasuries at the Fed {fmt_bn(ch)} over 13 weeks.")
    charts = [
        {"id": "gl_cb", "title": "Major central bank balance sheets in dollars", "units": "USD bn", "start": "2008-01-01",
         "series": [{"key": "G3_CB_USD", "label": "Fed + ECB + BoJ"}, {"key": "G2_CB_USD", "label": "ECB + BoJ"}],
         "source": "Federal Reserve, ECB, Bank of Japan, FX rates (via FRED)",
         "note": "The Fed is counted in Fed liquidity; only ECB + BoJ drive this pillar"},
        {"id": "gl_usd", "title": "US dollar (trade-weighted)", "units": "index", "start": "2006-01-01",
         "series": [{"key": "DTWEXBGS", "label": "Broad dollar"}], "source": "Federal Reserve H.10 (via FRED)"},
    ]
    return build_pillar(
        ctx, "global", "Global liquidity", ["G2_CB_USD", "DTWEXBGS"],
        ["G2_CB_USD", "ECBASSETSW", "JPNASSETS", "DTWEXBGS", "DEXJPUS", "DEXCHUS", "TRESEGCNM052N", "SWPT",
         "WMTSECL1", "WLRRAFOIAL", "BIS_USD_CREDIT"],
        blurb="Liquidity from other central banks and the price of dollars abroad.",
        drivers=drivers or ["Not enough data."],
        transmission="Foreign easing and a weaker dollar loosen global funding and push capital into risk assets, "
                     "including US ones. A strong dollar squeezes non-US dollar borrowers and EM.",
        classification="Creation abroad (ECB/BoJ assets) plus the price of dollar funding. The Fed is excluded "
                       "here to avoid double counting. PBOC is proxied by China's FX reserves.",
        timing="Leading for risk assets and EM (1–2 quarters).",
        charts=charts, extra=extra)
