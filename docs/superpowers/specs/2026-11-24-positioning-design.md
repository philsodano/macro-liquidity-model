# Positioning & leverage + simpler signals — Design

Date: 2026-11-24 · Status: approved in conversation (option A: free proxies; options greeks deferred)

## Intent
Add a "Positioning & leverage" part to Markets & risk that shows how exposed hedge funds, banks/dealers and
leveraged investors are, in plain words, so crowded or fragile positioning is visible next to the macro read.
Make signals simpler (one row: name, status chip, one line) and tighten dashboard wording.

## Goals
- Hedge funds: equity long/short ratio and net exposure, leverage (gross assets ÷ net assets), repo and prime-broker
  borrowing — SEC Form PF via the OFR Hedge Fund Monitor (quarterly, ~5-month lag; say so).
- Futures positioning (CFTC Traders in Financial Futures, weekly): leveraged funds' net position as % of open interest
  and long/short ratio in S&P 500, Nasdaq-100, Russell 2000, VIX and US dollar futures; asset managers in S&P 500.
- Treasury basis trade size: leveraged funds' net Treasury futures DV01 (OFR TFF aggregate, weekly).
- Investor leverage: FINRA margin debt (monthly), y/y change, margin debt net of free credit balances.
- Banks & dealers: primary dealer net Treasury positions (NY Fed, weekly), bank holdings of Treasury/agency securities
  (H.8), plus existing bank loans to nonbank lenders and regional bank stocks.
- Options proxies (no greeks): VIX vs 3-month VIX (curve shape), implied vs realised volatility, leveraged funds' VIX
  futures position. Each explained in one sentence.
- Three simple positioning signals scored into scenarios under a new `positioning` group (weight 0.3):
  crowding (equity), leverage/fragility (basis trade + margin debt), hedging demand (options proxies).

## Non-goals / anti-goals
- No options greeks or dealer gamma (needs a paid/registered chain; future upgrade via Tradier).
- No jargon without a plain explanation; no percentile shown without its history window.
- Never present Form PF data as current — always show its quarter and lag.

## Approach
Same pipeline: new sources `cftc` (Socrata JSON), `ofr` (HFM API), `nyfedpd` (Primary Dealer API), `finra` (xlsx);
registry entries; `macro/analytics/positioning.py` builds summaries + signals; snapshot key `positioning`; dashboard
renders it inside Markets & risk; weekly report mentions it under Financial Markets.

Signals UI: every signal row = name · chip (Supportive / Neutral / Headwind / Not counted) · first sentence of the
evidence; full evidence behind a details toggle. Section intros shortened; cross-asset meanings collapsed.

## Left to the builder
Exact thresholds (documented in code), chart choices, wording.
