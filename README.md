# Liquidity Cycle Monitor

A forward-looking US macro and markets model built around liquidity, monetary policy and the business cycle.
One data store and one analytics engine feed two outputs: an interactive dashboard and a weekly report.

**Dashboard:** https://claude.ai/artifact/3d4VEpJQumgSbYMzo9oy3j (private). Locally: `python -m http.server -d site`, then open http://localhost:8000.

## Quick start
```bash
pip install -e .            # pandas, numpy, requests, pyyaml, openpyxl, xlrd (+ pytest)
python -m macro refresh     # fetch due data into data/
python -m macro build       # model → site/snapshot.json + site/index.html + history/
python -m macro report      # weekly report → reports/YYYY-MM-DD.md
python -m macro all         # all three
python -m macro build --as-of 2022-06-30 --no-research   # point-in-time run (not saved)
python -m pytest -q         # 100+ tests; `-m network` adds the live-source check
```

## Architecture
```
config/indicators.yaml   221 series: source, units, frequency, cycle timing (leads/moves with/lags), polarity, what/why
config/settings.yaml     refresh cadence per source, freshness grace, scenario priors and weights, FOMC dates
macro/sources/           FRED/ALFRED, US Treasury Fiscal Data, NY Fed (incl. primary dealers), ECB, BoE, BIS, SEC XBRL, Tiingo,
                         CFTC futures positioning, OFR Hedge Fund Monitor (SEC Form PF), FINRA margin debt, research files
macro/store.py           data/series (current), data/vintages (every value ever seen + date first seen), data/meta
macro/liquidity/         six pillars → impulses → market / economy / all-pillar composites (no dollar double counting)
macro/analytics/         central banks, consumer & jobs, cycle, inflation, markets & risk pay, positioning & leverage,
                         cross-asset checks, allocation
macro/research/          transmission lags (bootstrap ranges), historical analogues, tests of the Druckenmiller principles
macro/scenarios.py       base/bull/bear from evidence (log-odds), floor 5% / cap 80%, bounded analyst override
macro/snapshot.py        the single JSON both outputs read; macro/narrative.py turns numbers into plain text
macro/render/            dashboard (static page + JSON) and weekly report (Markdown + HTML)
history/                 conclusions.jsonl (one line per run, drives "what changed"), snapshots/, overrides.json
```

## Liquidity framework
Six pillars, each with level, multi-horizon change, acceleration, drivers, transmission and timing:
Fed (net liquidity = Fed assets − Treasury cash − reverse repo), government spending, bank lending, private credit &
bonds, global (ECB + BoJ in dollars, the dollar), AI capex (hyperscaler capex and how it is funded).
Pillars combine as z-scores of their change, never as added dollars; the double-counting rules are listed on the
dashboard. **Market liquidity** (Fed, global, credit) is the measure that historically lined up with stocks
(back-test on the Research tab); **economy liquidity** (deficits, banks, AI capex) feeds growth with a longer lag.

## Data integrity
- Every metric shows source, observation date, date first seen, frequency and freshness (fresh / due / stale).
- Revisions are kept (`data/vintages`); `--as-of` runs use only values seen by that date. Before this model's own
  log began (Nov 2026), as-of runs use today's data cut at its usual publication date — revisions are not undone
  (flagged in the snapshot). ALFRED vintages can be pulled with `macro.sources.fred.fetch_vintage`.
- Missing official data is never filled in (October 2025 CPI was never published; y/y uses the latest computable month).
- Estimates (net liquidity, impulses, implied rate path, recession odds, ERP) are labelled as estimates.

## Updating
`refresh` fetches only what is due (cadence per source in `settings.yaml`). A weekly scheduled Claude session follows
`RUNBOOK.md`: refresh → build → test → bounded analyst notes → report → commit → republish the dashboard.

## Positioning & leverage (Markets & risk)
Hedge fund holdings (Form PF: net exposure, long/short ratio, leverage, repo and prime-broker borrowing — quarterly,
~5 months old, a backdrop for medium/long-term views), hedge fund futures bets (CFTC, weekly), margin debt (FINRA),
the Treasury basis trade, dealer and bank exposure, and options-market proxies (VIX curve, implied vs realised
volatility, VIX futures positioning). Three signals — crowding, leverage & fragility, options market — feed the
scenarios with weight 0.3.

## Limitations
- **Market prices (Tiingo) need a valid API key** — until then sector, size, style, gold, BDC and breadth panels are empty.
- No free fed funds futures: the priced rate path is read from the 1-year yield (includes term premium).
- No options greeks or dealer gamma (no free options chain here); options section uses proxies. Upgrade path: a
  registered options feed (e.g. a free Tradier developer token) added like the Tiingo key.
- No free earnings revisions / forward P/E; valuation uses Damodaran's implied ERP (monthly) and Shiller (to 2024).
- ICE high-yield spreads on FRED cover ~3 years; long history uses Moody's Baa.
- PBOC balance sheet is proxied by China's FX reserves; BoE balance sheet not included.
- Spending by income group has no free monthly source; the split uses delinquency, card tightening and wealth proxies.
- AI funding misses off-balance-sheet structures (joint ventures, leases not yet started).
- Allocation sensitivities and scenario weights are judgement, documented in code; back-tests are in-sample.
