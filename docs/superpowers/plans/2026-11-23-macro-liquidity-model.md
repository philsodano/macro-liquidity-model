# Macro Liquidity Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python pipeline that fetches official macro/market data with vintages, runs a liquidity-centred analytics
engine, and emits one JSON snapshot that drives a static interactive dashboard and a dated weekly report.

**Architecture:** `refresh` (fetchers → CSV store with vintage log) → `build` (transforms → liquidity engine →
analytics → scenarios → snapshot.json) → `render` (site/index.html with embedded snapshot; reports/YYYY-MM-DD.md).
A scheduled Claude cloud task runs the pipeline weekly, adds bounded analyst notes, commits and republishes.

**Tech Stack:** Python 3.13, pandas, numpy, requests, pyyaml, openpyxl, xlrd, pytest; ECharts (pinned, cdnjs) in the page.

**Spec:** `docs/superpowers/specs/2026-11-23-macro-liquidity-model-design.md`

## Global Constraints

- No secrets in code, config or env. Tiingo key is proxy-injected; code sends `Authorization: Token proxy-injected`.
- Outbound requests carry a generic User-Agent `macro-liquidity-model/0.1 (research use)`; no personal details.
- Every displayed metric has: source, observation date, first-seen/release date, frequency, freshness status.
- Never interpolate missing data for display; never treat estimates as actuals (`kind` field on every signal).
- Liquidity pillars are exclusive: no series is a core measure in two pillars.
- Scenario probabilities sum to 100 (±0.1), floor 5, cap 80; analyst override ≤ ±10pp per scenario, logged with reason.
- `--as-of DATE` runs must not use any observation first seen after DATE.

## Review Focus

1. A source is down, rate-limited or changes schema → the run continues, the series keeps its history, is flagged `stale`/`failed`, and nothing is overwritten with empty data. (Task 2 test `test_refresh_survives_failed_source`.)
2. A re-fetch returns revised values → current series updated, vintage log gains rows only for changed values, no duplicates. (Task 1 test `test_revision_appends_vintage`.)
3. Stale low-frequency inputs (quarterly data 4+ months old, or delayed releases after a shutdown) → flagged, and excluded from "current" composites with a visible note rather than silently used. (Task 3 `test_stale_input_excluded_from_composite`.)
4. Tiingo unavailable → market panels show "unavailable", build succeeds, scenario scoring renormalises over available evidence. (Task 7 `test_scenarios_with_missing_evidence`.)
5. As-of runs leaking future data → reconstructed series end at or before the as-of date and use only first-seen ≤ as-of values. (Task 1 `test_read_as_of_excludes_later_vintages`.)

---

### Task 1: Registry and vintage-aware store

**Files:**
- Create: `pyproject.toml`, `macro/__init__.py`, `macro/registry.py`, `macro/store.py`, `config/indicators.yaml` (initial schema + ~10 core series), `config/settings.yaml`
- Test: `tests/test_registry.py`, `tests/test_store.py`

**Interfaces:**
- Produces:
  - `Indicator` dataclass: `id, name, source, source_id, units, freq ('D'|'W'|'M'|'Q'), section, pillar|None, role ('core'|'member'|None), signal ('leading'|'coincident'|'lagging'), polarity (+1|-1), release_lag_days:int, transform ('level'|'yoy'|'diff'), scale:float, what:str, why:str, kind ('fact'|'estimate')`
  - `load_registry(path=Path('config/indicators.yaml')) -> dict[str, Indicator]` (raises `ValueError` on duplicate id, unknown freq/source, or a series that is `core` in two pillars)
  - `load_settings(path=Path('config/settings.yaml')) -> dict`
  - `Store(root: Path)`: `write(id, s: pd.Series, seen_at: date, origin='fetch') -> int` (number of new/changed obs); `read(id, as_of: date|None=None) -> pd.Series`; `meta(id) -> dict`; `set_meta(id, **kv)`; `ids() -> list[str]`
  - Files: `data/series/<id>.csv` (obs_date,value), `data/vintages/<id>.csv` (obs_date,value,seen_at,origin), `data/meta/<id>.json`

- [ ] **Step 1: Write failing tests**
  - `test_load_registry_rejects_duplicate_core` — yaml with one id `core` in pillars `central_bank` and `fiscal` → `ValueError`.
  - `test_write_then_read_roundtrip` — write 3 obs, read returns same values with `DatetimeIndex`.
  - `test_revision_appends_vintage` — write `{2026-09-01: 100}` seen 2026-10-03, then `{2026-09-01: 101, 2026-10-01: 102}` seen 2026-11-07 → `write` returns 2; vintages has 3 rows; current value 101.
  - `test_write_empty_series_is_noop` — empty series returns 0 and leaves files unchanged.
  - `test_read_as_of_excludes_later_vintages` — with the above, `read(id, as_of=date(2026,10,15))` == `{2026-09-01: 100}`.
- [ ] **Step 2: Run** `pytest tests/test_registry.py tests/test_store.py -v` → FAIL (module missing)
- [ ] **Step 3: Implement** registry and store. `read(as_of)` = for each obs_date, last vintage row with `seen_at <= as_of`.
- [ ] **Step 4: Run** same command → PASS
- [ ] **Step 5: Commit** `feat: indicator registry and vintage-aware CSV store`

### Task 2: Fetchers and refresh orchestration

**Files:**
- Create: `macro/http.py`, `macro/sources/{__init__,fred,alfred,treasury,nyfed,ecb,boe,sec,tiingo,files}.py`, `macro/refresh.py`, `macro/freshness.py`
- Test: `tests/test_sources.py` (offline fixtures in `tests/fixtures/`), `tests/test_refresh.py`, `tests/test_freshness.py`

**Interfaces:**
- Consumes: `Indicator`, `Store`
- Produces:
  - `get(url, params=None, headers=None, retries=3, timeout=30) -> requests.Response` (backoff on 429/5xx)
  - Each source module: `fetch(ind: Indicator, start: date|None) -> pd.Series` (float values, DatetimeIndex, already scaled by `ind.scale`). `SOURCES: dict[str, Callable]` in `macro/sources/__init__.py`.
  - `fred.fetch` uses `https://fred.stlouisfed.org/graph/fredgraph.csv?id=…`; `fred.last_updated(source_id) -> datetime|None` (series page "Updated:"); `alfred.fetch_vintage(source_id, vintage_date) -> pd.Series`; `alfred.first_release(source_id, start, end) -> pd.Series` (value as first published, via monthly vintages)
  - `treasury` (Fiscal Data: DTS TGA close, MTS deficit, MSPD/auctions), `nyfed` (RRP, SOFR, ACM term premium xls), `ecb` (SDMX csvdata), `boe` (IADB csv), `sec` (companyconcept JSON → quarterly values, de-cumulating YTD durations), `tiingo` (adjClose), `files` (Damodaran ERP xlsx)
  - `refresh(store, registry, settings, today: date, only_due=True, ids: list[str]|None=None) -> RefreshReport` with per-id `status ('updated'|'unchanged'|'skipped'|'failed')`, `new_obs`, `error`
  - `freshness(ind, last_obs: date|None, today: date) -> 'fresh'|'due'|'stale'|'missing'` — expected next obs = last_obs + period(freq) + release_lag_days; `due` if today ≤ expected + grace (settings), `stale` beyond.

- [ ] **Step 1: Failing tests**
  - `test_fred_csv_parse` (fixture with "." missing values → dropped, not zero).
  - `test_sec_decumulates_ytd` — fixture Q1 90-day 10, H1 181-day 25, 9M 50, FY 80 → quarters 10,15,25,30.
  - `test_refresh_survives_failed_source` — one fetcher raises → status `failed`, others `updated`, failed series files untouched.
  - `test_freshness_states` — monthly series, lag 35: last_obs 2026-09-01, today 2026-11-10 → `fresh`; today 2026-12-20 → `stale`; None → `missing`.
  - `test_refresh_respects_frequency` — source refreshed yesterday with settings `weekly` → `skipped` when `only_due`.
- [ ] **Step 2: Run** `pytest tests/test_sources.py tests/test_refresh.py tests/test_freshness.py -v` → FAIL
- [ ] **Step 3: Implement** modules above.
- [ ] **Step 4: Run** → PASS; then live smoke: `python -m macro refresh --ids WALCL,RRPONTSYD,TGA_DAILY,SPY` prints statuses.
- [ ] **Step 5: Commit** `feat: source fetchers, refresh orchestration, freshness`

### Task 3: Full indicator registry and transforms

**Files:**
- Modify: `config/indicators.yaml` (full set, ~150 series across sections A–H, each with what/why/signal/polarity)
- Create: `macro/transforms.py`
- Test: `tests/test_transforms.py`, `tests/test_registry_live.py` (marked `network`)

**Interfaces:**
- Produces:
  - `change(s, horizon: str) -> float|None` (horizon in `'4w','13w','26w','52w','1m','3m','6m','12m'`; uses nearest obs at or before target date; None if insufficient)
  - `pct_change(s, horizon) -> float|None`; `ann_rate(s, months:int) -> pd.Series`; `yoy(s) -> pd.Series`
  - `acceleration(s, horizon) -> float|None` = change over horizon now minus change over same horizon one horizon ago
  - `zscore(s, years=10) -> pd.Series`; `percentile(s, years=20) -> float`
  - `to_period(s, freq='W'|'M'|'Q', how='last'|'mean') -> pd.Series`
  - `summarize(ind, s, today) -> dict` with keys `latest, obs_date, first_seen, changes{h: v}, pct_changes, accel, z, pctile, direction ('up'|'down'|'flat'), freshness, signal, kind, units, source, freq`
- [ ] **Step 1: Failing tests** — `test_change_horizons_weekly`, `test_ann_rate_monthly` (1% m/m for 3m → 12.68%), `test_acceleration_sign`, `test_percentile_bounds`, `test_summary_has_all_metadata_keys`, `test_stale_input_excluded_from_composite` (helper `usable(summary) -> bool` false for `stale`/`missing`).
- [ ] **Step 2–4:** run → FAIL, implement, run → PASS. Live: `pytest -m network tests/test_registry_live.py` fetches every registry id once and reports any that fail; fix ids until all pass or are explicitly marked `unavailable: <reason>` in the yaml.
- [ ] **Step 5: Commit** `feat: full indicator registry and transforms`

### Task 4: Liquidity engine

**Files:**
- Create: `macro/liquidity/{__init__,central_bank,fiscal,banking,private_credit,global_liq,ai_capex,consolidate}.py`
- Test: `tests/test_liquidity.py`

**Interfaces:**
- Consumes: `Store.read`, `transforms.*`, registry `pillar`/`role`
- Produces:
  - `net_liquidity(walcl, tga, rrp) -> pd.Series` (weekly Wed, USD bn; all inputs converted to USD bn first)
  - `g4_balance_sheets(fed, ecb, boj, boe, eurusd, usdjpy, gbpusd) -> pd.DataFrame` columns `usd_total, local_growth_contrib, fx_contrib` (13w change decomposition)
  - `credit_impulse(credit_level, ngdp) -> pd.Series` = Δ(12m flow)/NGDP, pp
  - `fiscal_impulse(deficit_12m, ngdp) -> pd.Series` = Δ12m of deficit/NGDP, pp (+ = expansionary)
  - `ai_funding_split(company_quarters: pd.DataFrame) -> pd.DataFrame` columns `capex, ocf, debt_net, buybacks_div, lease_principal, internal_share, external_share` (all `kind='estimate'` where derived)
  - Each pillar module: `assess(store, registry, today) -> Pillar` dict: `id, title, core_series, impulse (z of 13w/26w change, sign-adjusted), accel, state ('adding'|'draining'|'neutral'), drivers: list[str], transmission: str, signal_class, members: list[summary], charts: list[chart spec]`
  - `consolidate(pillars) -> dict` with `composite` (equal-weight mean of available impulses), `breadth` (n adding − n draining), `composite_history` (weekly series), `accel`, `regime ('improving'|'deteriorating'|'stable')`, `excluded` (stale pillars), `aggregation_notes`
- [ ] **Step 1: Failing tests**
  - `test_net_liquidity_identity` — WALCL 7000, TGA 800, RRP 200 → 6000.
  - `test_pillars_exclusive` — loaded registry: every `core` id appears in exactly one pillar.
  - `test_tga_counted_once` — TGA is `core` only in central_bank; in fiscal it is `member` with `display_only: true`.
  - `test_g4_fx_decomposition_sums` — local + fx contributions == total change (±1e-6).
  - `test_composite_ignores_stale_pillar` — one pillar stale → excluded and listed in `excluded`.
  - `test_detects_turn` — synthetic net liquidity falling 10 weeks then rising → `regime == 'improving'`, `accel > 0`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat: liquidity engine with six pillars and consolidation`

### Task 5: Macro analytics (central banks, consumer, cycle, inflation, markets, cross-asset)

**Files:**
- Create: `macro/analytics/{__init__,signals,central_banks,consumer,cycle,inflation,markets,cross_asset,allocation}.py`
- Test: `tests/test_analytics.py`

**Interfaces:**
- Produces:
  - `Signal` dataclass: `id, label, score (-2..2), state ('positive'|'negative'|'neutral'|'mixed'), evidence: str, kind ('fact'|'estimate'|'interpretation'|'hypothesis'), horizon ('leading'|'coincident'|'lagging')`
  - Each module: `assess(store, registry, today) -> dict` with `summaries`, `signals: list[Signal]`, `charts`, `notes`
  - `central_banks`: real policy rate (EFFR − core PCE y/y, and − 1y expectations), implied path estimate (3m/6m/1y bills & 2y vs EFFR, labelled estimate), ECB/BoJ/BoE/PBOC lines
  - `cycle.recession_prob(spread_10y3m_monthly) -> float` = Φ(−0.5333 − 0.6330·spread); `cycle.classify(signals) -> dict(phase, quadrant, mixed: bool, dispersion, evidence)`; mixed when dispersion of growth z-scores > `settings.cycle.mixed_threshold` or level and direction conflict
  - `inflation.decompose()` → demand vs supply heuristic, `kind='interpretation'`
  - `markets`: ERP (Damodaran implied; EY − real 10y), spread percentiles vs recession prob, VIX − realised vol, breadth (RSP/SPY), size (IWM/SPY), sector relative strength table
  - `cross_asset.matrix(snapshot_parts) -> list[dict(test, expected, observed, verdict ('confirm'|'diverge'|'neutral'|'n/a'), meaning)]`
  - `allocation.assess(parts) -> list[dict(asset, score -2..2, thesis, why, priced_in, invalidation, confirmation)]` for the 12 asset classes and sector list in the spec
- [ ] **Step 1: Failing tests** — `test_recession_prob_known_values` (spread 0 → 29.7%; spread −1 → 45.0%), `test_cycle_mixed_when_dispersed`, `test_real_rate_uses_core_pce`, `test_cross_asset_na_when_missing` (no Tiingo data → verdict `n/a`), `test_allocation_covers_all_assets`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat: macro analytics, cross-asset tests, allocation framework`

### Task 6: Lags, analogues and principle backtests

**Files:**
- Create: `macro/research/{__init__,lags,analogues,backtest}.py`
- Test: `tests/test_research.py`

**Interfaces:**
- Produces:
  - `lead_lag(x: pd.Series, y: pd.Series, max_lag: int=24, n_boot=500, block=6) -> dict(best_lag, corr, ci=(lo,hi), n, all_lags)` on monthly data
  - `TRANSMISSION_PAIRS` (policy rate→unemployment, credit impulse→real GDP, SLOOS→C&I loans, fiscal impulse→real PCE, net issuance→term premium, consumer credit→retail sales, capex orders→investment) and `estimate_lags(store) -> list[dict]`
  - `feature_matrix(store) -> pd.DataFrame` (monthly 1990+: FF 12m Δ, real FF, 10y–3m, Fed/monetary base 12m %, Baa–10y and 6m Δ, unemployment 6m Δ, core PCE y/y, IP y/y); `nearest(features, date, k=5, exclude_months=24) -> list[dict(date, distance, next12m: dict)]`; `named_regimes(features) -> list[dict]` for 1994, 1998, 2000–02, 2008, 2018, 2020, 2022
  - `principle_tests(store) -> list[dict(principle, test, result, hit_rate, n, failures: list[period], verdict)]` covering: liquidity direction vs level, acceleration, 12–18m forward horizon, credit leads growth, divergence
- [ ] **Step 1: Failing tests** — `test_lead_lag_recovers_known_lag` (y = x shifted 6 + noise → best_lag 6, ci contains 6), `test_nearest_excludes_adjacent_months`, `test_named_regimes_complete`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat: transmission lags, historical analogues, principle tests`

### Task 7: Scenarios and conclusion history

**Files:**
- Create: `macro/scenarios.py`, `macro/history.py`; `history/overrides.json` (empty list)
- Test: `tests/test_scenarios.py`, `tests/test_history.py`

**Interfaces:**
- Consumes: all `Signal`s
- Produces:
  - `score(signals, settings) -> dict(model: {base,bull,bear}, override: {..}|None, final: {..}, contributions: list[dict(signal, effect on each scenario)])` — log-odds = log(prior) + Σ sensitivity[scenario][signal_group]·score; softmax; floor 5 / cap 80; renormalise; groups with no signals contribute 0
  - `apply_override(model_probs, override: dict(date, deltas, reason)) -> dict` (rejects |delta| > 10 or missing reason)
  - `scenario_text(settings) -> dict` (economic, liquidity, central bank, consumer, markets, confirm, invalidate per scenario; from `settings.yaml`)
  - `history.append(record, path='history/conclusions.jsonl')`; `history.previous(path, before: date) -> dict|None`; `history.diff(prev, cur) -> list[dict(field, before, after, why)]`
- [ ] **Step 1: Failing tests** — `test_probs_sum_to_100`, `test_floor_and_cap`, `test_scenarios_with_missing_evidence`, `test_override_bounds` (11pp → ValueError), `test_diff_reports_prob_change_with_drivers`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat: evidence-scored scenarios and conclusion history`

### Task 8: Snapshot and CLI

**Files:**
- Create: `macro/snapshot.py`, `macro/__main__.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Produces:
  - `build_snapshot(store, registry, settings, as_of: date) -> dict` keys: `schema_version, meta{as_of, built_at, mode ('live'|'as_of')}, executive, central_banks, liquidity, consumer, cycle, inflation, markets, cross_asset, allocation, scenarios, research{lags, analogues, principles}, changes, data_quality[], series{id: [[date, value], …]}`; writes `site/snapshot.json`
  - CLI: `python -m macro refresh [--ids] [--force]`, `build [--as-of]`, `report`, `all`
- [ ] **Step 1: Failing tests** — `test_snapshot_keys`, `test_every_displayed_metric_has_metadata` (walk snapshot; every summary has source/obs_date/first_seen/freq/freshness), `test_as_of_snapshot_has_no_future_obs`.
- [ ] **Step 2–4:** FAIL → implement → PASS; live `python -m macro all` completes.
- [ ] **Step 5: Commit** `feat: snapshot assembly and CLI`

### Task 9: Dashboard

**Files:**
- Create: `macro/render/dashboard.py`, `macro/render/templates/dashboard.html` (+ inline CSS/JS)
- Test: `tests/test_render.py`; Playwright screenshot check script `scripts/check_dashboard.py`

**Interfaces:**
- Consumes: snapshot dict, report history list
- Produces: `render_dashboard(snapshot, reports: list[dict(date, md, html)], out=Path('site/index.html')) -> Path`
- Layout: header (as-of, data status, thesis); tabs A Executive · B Central banks · C Liquidity engine · D Consumer & labour · E Cycle · F Inflation · G Markets & risk · H Allocation · Research (lags, analogues, principle tests) · Reports · Data & methods. Expandable `<details>` for depth. Each chart: title, units, axis labels, date range, source line.
- [ ] **Step 1: Failing tests** — `test_render_contains_all_tabs`, `test_every_chart_has_source_and_units`.
- [ ] **Step 2–4:** FAIL → implement → PASS; run `scripts/check_dashboard.py` → no console errors, screenshots of each tab reviewed at 1440 and 390 px.
- [ ] **Step 5: Commit** `feat: static interactive dashboard`

### Task 10: Weekly report, runbook, scheduled task, end-to-end verification

**Files:**
- Create: `macro/render/report.py`, `notes/README.md`, `RUNBOOK.md`, `README.md`, `scripts/weekly.sh`
- Test: `tests/test_report.py`, `tests/test_historical.py` (marked `network`)

**Interfaces:**
- Produces: `render_report(snapshot, prev_snapshot|None, notes_md: str|None) -> str` with the 8 required sections in order; `reports/YYYY-MM-DD.md`; analyst notes read from `notes/YYYY-MM-DD.md` and labelled "Analyst interpretation".
- [ ] **Step 1: Failing tests** — `test_report_sections_in_order`, `test_report_uses_same_snapshot_numbers` (composite value in report == snapshot), `test_report_highlights_changes`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Historical regime tests** — `test_historical.py`: as-of 2018-12-31 central-bank pillar draining; 2019-09-30 money-market stress flagged; 2020-04-30 composite strongly adding; 2022-06-30 draining with negative acceleration; 2023-03-31 BTFP/discount-window jump detected as reversal. Run `pytest -m network tests/test_historical.py -v` → PASS (or documented failures with explanation).
- [ ] **Step 6: Final checks** — the eight checks in the request, each with command output recorded in `docs/verification.md`.
- [ ] **Step 7: Commit, push to `philsodano/macro-liquidity-model`, publish dashboard as private page, create weekly scheduled task.**
