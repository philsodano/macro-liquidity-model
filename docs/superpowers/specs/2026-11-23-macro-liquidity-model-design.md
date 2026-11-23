# Macro Liquidity Model — Design

Date: 2026-11-23 · Status: approved in conversation (approach, architecture, Tiingo for market data)

## Intent

A continuous, forward-looking (12–18 month) US macro and markets outlook model, built around liquidity, monetary
policy and the business cycle, in the tradition of Druckenmiller's Lost Tree Club (Jan 2015) and Nov 2018 remarks —
but with each principle tested against history rather than assumed. It must answer:

1. Where are we in the economic and financial cycle?
2. Where is liquidity being created, destroyed and distributed?
3. What does that imply for growth, inflation, earnings and financial conditions?
4. Which asset classes, sectors and industries benefit or suffer?
5. Where is risk adequately compensated and where is it mispriced?

The output is an investment outlook, not a data summary.

## Goals

- One data store and one analytics engine feeding two outputs: an interactive dashboard and a weekly report.
- Liquidity engine as the centrepiece: six pillars, direction and acceleration, additive vs subtractive, transmission.
- Every metric carries source, observation date, release/first-seen date, frequency and freshness status.
- Revisions preserved (vintage log); historical tests use ALFRED first-release data where it exists.
- Base / bull / bear scenarios with probabilities that sum to 100 and change only with evidence; every change logged.
- Dated history of weekly reports and of model conclusions.

## Non-goals

Intraday signals, execution, single-stock valuation, unsupported predictions, one liquidity number presented as the
whole truth, long commentary without investment implications.

## Anti-goals (failure even if it "works")

- Presenting stale data as current, or estimates as actuals.
- Summing incompatible liquidity measures (double counting TGA in both "Fed" and "fiscal", adding reserves to net
  liquidity, adding H.8 deposits to M2, etc.).
- Forcing a cycle label when evidence is mixed.
- A narrative that ignores conflicting signals.

## Constraints

- Runs in an ephemeral cloud container. Durable state lives in a private GitHub repo (`philsodano/macro-liquidity-model`).
- Free/official data sources first. Reachable and verified: FRED (CSV endpoint, no key), ALFRED (vintage CSV), Treasury
  Fiscal Data API, NY Fed Markets API and data files, ECB Data API, BoE IADB, BLS API, SEC XBRL API (requires a
  descriptive User-Agent), Damodaran ERP, BIS stats API. Market prices: Tiingo (key injected by the session proxy as
  `Authorization: Token …`; never stored in code or env).
- Not available free: fed funds futures (rate path estimated from bills/2y and labelled as estimate), sell-side earnings
  revisions, forward P/E, leveraged-loan indices, private credit fund flows. ICE BofA spreads on FRED cover ~3 years only
  → long-history analogues use Moody's Baa–10y.
- Python 3.13; minimal dependencies (pandas, numpy, requests, pyyaml, openpyxl/xlrd for xls, pytest).

## Approaches considered

| Approach | Trade-off | Decision |
|---|---|---|
| **Python pipeline → JSON snapshot → static single-file HTML dashboard + Markdown/HTML report; scheduled Claude cloud task refreshes, commits, republishes as a private claude.ai page** | Private, durable, no server; analyst commentary each week; dashboard is static between refreshes | **Chosen** |
| Streamlit/Dash app | Rich interactivity but needs a running server; nowhere private to host it | Rejected |
| Next.js on Vercel + GitHub Actions cron | Always-on, but public unless protected; more moving parts; commentary rule-only | Rejected |
| GitHub Actions-only refresh | Deterministic, free, but no analyst pass; Pages is public | Kept as optional fallback (workflow file can be added) |

## Architecture

```
config/indicators.yaml      registry: every series, its source, units, freq, category, lead/coincident/lag, polarity, rationale
config/settings.yaml        refresh frequencies per source, lookbacks, thresholds, scenario priors
macro/sources/*.py          fetchers (fred, alfred, treasury, nyfed, ecb, boe, bls, sec, tiingo, damodaran, bis)
macro/store.py              CSV store: data/series/<id>.csv (obs_date,value) + data/vintages/<id>.csv (append-only log)
                            + data/meta/<id>.json (source, last_fetch, last_new_obs_at, release date where known)
macro/transforms.py         changes over 4w/13w/26w/52w, YoY, 3m/6m annualised, acceleration, z-scores, percentiles
macro/liquidity/            six pillars + consolidation rules + impulse
macro/analytics/            regime, inflation, consumer, credit, risk compensation, cross-asset, lags, analogues, backtest
macro/scenarios.py          evidence → likelihood scoring → probabilities; change log
macro/snapshot.py           one JSON snapshot = the single source of truth for both outputs
macro/render/dashboard.py   static HTML (embedded snapshot + charts)
macro/render/report.py      weekly report (Markdown + HTML), dated
history/conclusions.jsonl   one line per run: regime, liquidity state, scenario probs, key signals, overrides + reasons
reports/YYYY-MM-DD.md       weekly reports
site/index.html             built dashboard (published as the private page)
tests/                      unit + historical-regime tests
```

CLI: `python -m macro refresh | build | report | backtest | all` with `--as-of` for point-in-time runs.

## Data integrity rules

- Observation date ≠ release date. Each series stores `obs_date`; metadata stores `first_seen_at` per observation
  (from our vintage log) and, for FRED, the series "last updated" timestamp.
- Freshness: each series has an expected release lag in the registry; status = fresh / due / stale / missing.
- Market data is labelled "market close (daily)"; released statistics labelled "release".
- Estimates (implied rate path, fiscal impulse, AI funding split, implied ERP) are labelled `estimate` with method.
- Missing data is shown as missing, never interpolated for display. Mixed-frequency comparisons are aligned explicitly
  (e.g. weekly → month-end) and the alignment is stated.

## Liquidity framework (centrepiece)

Six pillars. Each reports level, history, change over several horizons, acceleration, drivers, additive/subtractive
classification and transmission channel.

1. **Central bank:** Fed total assets (WALCL), securities held, reserves (WRESBAL), TGA (WTREGEN + daily DTS), ON RRP
   (RRPONTSYD / NY Fed), QT pace (13-week change in SOMA holdings), SOFR–IORB spread (money-market stress), standing repo
   usage. **Fed net liquidity = WALCL − TGA − ON RRP** (an identity-based proxy for reserves + currency; shown with its
   limitations).
2. **Fiscal:** monthly deficit (MTS, 12m rolling), fiscal impulse (change in deficit/GDP), net marketable issuance by bills
   vs coupons (Fiscal Data / MSPD), average maturity, interest outlays. TGA is a *driver* displayed here but *counted* only
   in pillar 1.
3. **Banking:** H.8 loans & leases, C&I, CRE, consumer, loans to nondepository financial institutions (bank funding of
   private credit), deposits, M2, SLOOS standards/demand, bank credit impulse.
4. **Private credit & capital markets:** HY/IG OAS (3y) and Baa–10y (long history), nonfinancial corporate debt (Z.1),
   BDC proxies (BIZD price via Tiingo; BDC filings), HYG/LQD/BKLN/SRLN flows-of-price proxies, securitisation (Z.1 ABS),
   NBFI exposure from H.8. Classified as **distribution/re-intermediation**, not creation, except where funded by bank
   credit (counted in pillar 3 only).
5. **Global:** ECB, BoJ, BoE balance sheets (local currency growth and USD-translated), PBOC proxy (China FX reserves),
   broad dollar, Fed swap lines, foreign repo pool, custody holdings of Treasuries, BIS global liquidity (USD credit to
   non-US non-banks).
6. **AI capex:** hyperscaler capex, operating cash flow, debt issuance, finance leases and buybacks (SEC XBRL); data-center
   construction (Census via FRED where available), information-processing equipment investment (BEA), semiconductor
   output (IP). Funding split: internal cash flow (redistribution, not creation), bonds (credit, mostly redistribution of
   savings), bank loans (creation; pillar 3), equity, off-balance-sheet (leases/SPVs) flagged separately.

**Consolidation without double counting:**
- Dollar sums only where units and economic meaning match: (a) Fed net liquidity; (b) G4 central-bank balance sheets in
  USD with FX translation effect separated.
- Everything else is aggregated as standardised *impulses*: for each pillar, z-score of the 13w/26w change in its core
  measure (sign-adjusted so + = adding liquidity), then an equal-weighted composite plus a breadth count (pillars
  improving). Pillar membership is exclusive; a test asserts no series is in two pillars' core measure.
- Liquidity **impulse** = change in the flow; **acceleration** = change in the impulse. Both reported on 4w/13w/26w/52w.
- Lead/lag classification per indicator, from the registry and validated by lag analysis.

## Other components

- **Central banks:** nominal vs real policy rate (vs core PCE and 1y expectations), market-implied path (estimate from
  3m/6m/1y bills and 2y vs EFFR), balance sheet, reserves, financial conditions (NFCI, ANFCI), ECB/BoJ/BoE/PBOC.
- **Consumer & employment:** all listed series; employment flagged coincident/lagging; real vs nominal; income-group split
  via the NY Fed HHDC delinquency by age/region proxies and the Fed DFA (wealth by income percentile) where reachable.
- **Business cycle:** growth momentum composite (level vs trend × direction) and an inflation axis → regime quadrants,
  with a **mixed/divergent** state when indicator dispersion is high. Recession indicators: 10y–3m probit (NY Fed
  methodology, recomputed), Sahm rule, claims.
- **Inflation:** CPI/PCE headline/core, shelter, supercore, wages, energy, import prices, expectations; demand- vs
  supply-driven split (heuristic: core services ex-shelter & wages vs goods/energy/import prices), labelled as an
  interpretation.
- **Markets & risk compensation:** curve, real yields, ACM term premium, spreads vs recession probability, ERP (Damodaran
  implied and earnings-yield-minus-real-yield), VIX vs realised, breadth proxies (RSP/SPY), small vs large (IWM/SPY),
  sectors (XL*), dollar, gold, oil, copper, bitcoin.
- **Cross-asset confirmation:** a matrix of explicit tests (credit vs liquidity, dollar vs global conditions, real yields
  vs equity multiple, gold vs real yields, copper/oil vs growth, breadth vs index) → confirm / diverge / neutral.
- **Transmission lags:** cross-correlation of drivers (policy rate, credit impulse, SLOOS, fiscal impulse, issuance,
  consumer credit, capex) with targets, peak lag and bootstrap range; published with uncertainty.
- **Historical analogues:** standardised feature vector; nearest-neighbour months since 1990; named regimes (1994, 1998,
  2000–02, 2008, 2018, 2020, 2022) compared on the same indicators with what happened next 12 months.
- **Principle tests (backtest):** does liquidity impulse lead equity returns, credit spreads and growth? Hit rates and
  failures by regime — reported honestly, including where the Druckenmiller principles fail.

## Scenarios

- Base, bull, bear defined in `settings.yaml` with priors.
- Each evidence signal (liquidity impulse, credit, growth, inflation, labour, valuation) maps to a likelihood
  ratio per scenario; posterior = normalised prior × likelihoods, with a floor (5%) and cap (80%).
- The weekly Claude run may adjust any probability by at most ±10pp with a written reason; adjustments are stored
  separately from the model output and both are shown.
- Each scenario: economic, liquidity, central-bank, consumer assumptions, market implications, confirm/invalidate
  indicators. Base-case invalidation triggers listed explicitly.

## Updating

- `settings.yaml` sets refresh frequency per source (default: market daily, weekly H.4.1/H.8/claims, monthly releases on
  schedule). `refresh` only fetches sources that are due.
- Scheduled Claude cloud task (weekly, after Thursday H.4.1 and Friday data): clone repo, `refresh`, `build`, run tests,
  write the analyst sections of the weekly report, commit, republish the private dashboard page.
- `history/conclusions.jsonl` drives "what changed since last update".

## Left to the builder

Chart library (pinned CDN), exact page layout, specific series where FRED IDs need verification, thresholds tuned to
history and documented.
