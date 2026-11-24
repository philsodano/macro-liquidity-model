# Positioning & Leverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add hedge fund / bank / options-proxy positioning to Markets & risk, score it as simple signals, and tighten dashboard wording.

**Architecture:** Four new fetchers feed new registry series; `macro/analytics/positioning.py` turns them into plain-English readings and three signals (new scenario group `positioning`); snapshot key `positioning` renders inside Markets & risk and in the weekly report.

**Tech Stack:** Python 3.13, pandas, requests, openpyxl; existing static dashboard template.

**Spec:** `docs/superpowers/specs/2026-11-24-positioning-design.md`

## Global Constraints
- Every number shows source, observation date and frequency; Form PF always labelled "quarterly, ~5 months old".
- Plain words first; any term of art (DV01, open interest, basis trade) gets a one-sentence explanation next to it.
- No options greeks; options section uses VIX/VIX3M, implied − realised volatility, leveraged-fund VIX futures.
- Scenario weight for `positioning` = 0.3; signals with stale inputs are not counted (existing `apply_freshness`).

## Review Focus
1. CFTC returns a week with zero open interest or a missing field → that week is skipped, not divided by zero. (Task 1 `test_cftc_skips_zero_oi`.)
2. OFR series end quarters ago → shown with their quarter, marked by freshness; never treated as this week's data. (Task 2 `test_form_pf_labelled_with_quarter`.)
3. FINRA sheet columns renamed → fetch fails loudly (refresh marks failed), history kept. (Task 1 `test_finra_missing_column_raises`.)
4. Positioning inputs missing (source down) → section renders "No data", build succeeds, signals marked unavailable. (Task 2 `test_positioning_with_no_data`.)
5. Long/short ratio with zero shorts → None, not infinity. (Task 2 `test_ls_ratio_zero_short`.)

---

### Task 1: New sources and registry series

**Files:** Create `macro/sources/{cftc,ofr,nyfedpd,finra}.py`, fixtures in `tests/fixtures/`; Modify `macro/sources/__init__.py`, `macro/registry.py` (SOURCES), `config/indicators.yaml`, `config/settings.yaml` (refresh_days); Test `tests/test_sources_positioning.py`

**Interfaces — Produces:**
- `cftc.parse(rows: list[dict], metric: str) -> pd.Series`; metric ∈ `lev_net_pct` ((lev long − lev short) ÷ open interest × 100), `lev_ls` (lev long ÷ lev short), `am_net_pct` (asset managers, same formula). `cftc.fetch(ind, start)` with `source_id = "<contract_code>:<metric>"` (codes: ES 13874A, NQ 209742, RTY 239742, VIX 1170E1, DX 098662), Socrata `gpe5-46if`.
- `ofr.parse(payload: list) -> pd.Series`; `ofr.fetch` for mnemonics `FPF-ASSETCLASS_EQUITIES_LGNE_SUM`, `..._SGNE_SUM`, `FPF-ALLQHF_GAV_SUM`, `FPF-ALLQHF_NAV_SUM`, `FPF-BORROW_REPO_SUM`, `FPF-BORROW_PRIMEBROKER_SUM`, `TFF-LF_TREAS_NET_DV01`.
- `nyfedpd.parse(payload: dict) -> pd.Series`; series `PDPOSGST-TOT` (USD mn → bn).
- `finra.parse(content: bytes, column: str) -> pd.Series` (Year-Month → month start; USD mn → bn); columns "Debit Balances in Customers' Securities Margin Accounts", "Free Credit Balances in Customers' Securities Margin Accounts", "Free Credit Balances in Customers' Cash Accounts".
- FRED adds `VXVCLS` (VIX 3-month), `TASACBW027SBOG` (bank Treasury & agency securities).

- [ ] Step 1: failing tests — `test_cftc_net_pct_and_ls` (long 300, short 100, OI 1000 → net 20.0, ls 3.0), `test_cftc_skips_zero_oi`, `test_ofr_parse`, `test_nyfedpd_parse_bn`, `test_finra_parse_month_start_bn`, `test_finra_missing_column_raises`.
- [ ] Step 2: run `pytest tests/test_sources_positioning.py` → FAIL. Step 3: implement. Step 4: PASS; live `python -m macro refresh --force --ids <new ids>` → all updated.
- [ ] Step 5: commit `feat: positioning sources (CFTC, OFR Form PF, NY Fed dealers, FINRA margin)`.

### Task 2: Positioning analytics and signals

**Files:** Create `macro/analytics/positioning.py`; Modify `macro/analytics/__init__.py`, `macro/analytics/signals.py` (GROUPS), `config/settings.yaml` (weights.positioning: 0.3); Test `tests/test_positioning.py`

**Interfaces — Produces:** `positioning.assess(ctx) -> dict` with keys `hedge_funds`, `futures`, `leverage`, `banks`, `options` (each `list[dict(label, value, unit, detail, plain, pctile, years, obs_date, period, freshness, source)]`), `signals: list[Signal]` (ids `crowding`, `fragility`, `hedging`; group `positioning`), `charts`, `summary: str`. Derived series put on ctx: `HF_LS_RATIO`, `HF_NET_EXPOSURE`, `HF_LEVERAGE`, `VIX_TERM` (VIX ÷ VIX3M), `MARGIN_NET`.
- Crowding score = −mean(z of ES leveraged-fund net % OI (3y), HF net exposure pctile→z, margin debt y/y z) — crowded long is a headwind.
- Fragility score = −mean(z of |basis DV01| (3y), margin net y/y z).
- Hedging score: VIX_TERM > 1.0 → −1 (stress now); 0.9–1.0 → −0.3; < 0.85 and VIX pctile < 30 → −0.5 (complacent); else 0.

- [ ] Step 1: failing tests — `test_ls_ratio_zero_short` (None), `test_net_exposure_formula` (L 300, S 100 → 50.0%), `test_form_pf_labelled_with_quarter` ("2026 Q2" in item period), `test_positioning_with_no_data` (empty store → all items "No data", signals unavailable), `test_hedging_inverted_curve_is_headwind`.
- [ ] Steps 2–4: FAIL → implement → PASS; full suite green.
- [ ] Step 5: commit `feat: positioning analytics and signals`.

### Task 3: Snapshot, report, dashboard, wording

**Files:** Modify `macro/snapshot.py` (key `positioning`, charts), `macro/render/report.py` (Financial Markets: positioning lines), `macro/render/templates/dashboard.html` (Positioning block in Markets & risk; simple signal rows; shorter intros; cross-asset meanings collapsed; risk-paid lists merged), `scripts/check_dashboard.js` (ignore expected empty-report text); Test `tests/test_render.py`, `tests/test_report.py`

- [ ] Step 1: failing tests — `test_snapshot_has_positioning` (keys present, `positioning` in charts sections), `test_report_mentions_positioning` ("Positioning" in Financial Markets section).
- [ ] Steps 2–4: FAIL → implement → PASS; `python -m macro build && python -m macro report`; `node scripts/check_dashboard.js` → no console errors, no overflow; look at Markets screenshot once.
- [ ] Step 5: commit, push `main`, republish dashboard.
