# Verification
Run against snapshot 2026-11-23 (built 2026-11-23T21:51:56).

## 1. Liquidity framework works and avoids double counting
- Tests: `8 passed, 94 deselected in 0.54s`
- Spot check 2026-11-18: Fed assets 6,741.5 − Treasury cash 916.6 − RRP 0.4 = 5,824.4 bn; snapshot NETLIQ = 5,824.5.
- Rules enforced: Pillars are combined as standardised impulses (direction and speed), never by adding dollar amounts. / Dollar totals are shown only where units match: Fed net liquidity, and ECB + BoJ in dollars. / Treasury cash and reverse repo are counted once, inside Fed net liquidity — not again under fiscal. / Bank reserves are shown but not added to net liquidity (they are mostly the same money). …

## 2. Central bank, fiscal, banking, private credit, global and AI financing are all represented
- Fed liquidity: neutral, stable; 11 indicators; core = Fed balance sheet minus Treasury cash minus reverse repo.
- Government spending: neutral, stable; 9 indicators; core = Budget deficit, last 12 months.
- Bank lending: neutral, stable; 12 indicators; core = Bank lending + securities.
- Private credit & bonds: neutral, stable; 13 indicators; core = Corporate bond spread (long history).
- Global liquidity: draining, deteriorating; 11 indicators; core = Foreign central bank balance sheets ($), US dollar (trade-weighted).
- AI investment: adding, improving; 8 indicators; core = Big Tech AI capex.

## 3. Consumer and employment indicators with leading/coincident/lagging labels
- 30 series: {'coincident': 13, 'leading': 8, 'lagging': 9}. Payrolls coincident, unemployment lagging, claims/temps/hours/quits leading.
- Live diagnosis: dissaving — Spending is outrunning real income; households are saving less to keep spending.

## 4. Tested against historical regimes
- Regime tests (2018 QT, 2019 repo, 2020 flood, 2022 tightening, 2023 bank stress, 2026 RRP): `6 passed, 96 deselected in 20.59s`
- Liquidity drives market direction: **Supported**. Market liquidity since 2002-06: stocks rose 9.18% in the 6 months after a positive reading vs 1.06% after a negative one; it picked above-average periods 67.9% of the time. The all-pillar average managed 43.4% and the economy pillars 43.5% — liquidity works for markets only when measured the right way. Long-history money/credit proxy (since 1989-06): 58.4%.
- Direction and acceleration matter more than level: **Not supported**. Correlations with next-6m returns — level +0.20, change -0.02, acceleration -0.17. Strongest: level. All are weak in absolute terms.
- Look 12–18 months ahead: **Supported**. Liquidity lines up best with stocks 12m ahead and with industrial output 12m ahead. Both peak at similar horizons here; the 12–18-month lens holds for the economy.
- Credit exposes weakness before the economy does: **Supported**. Credit spreads warned a median 10 months before recessions began; the jobs-based Sahm rule fired a median 1 month(s) after they began. Widening spreads lead rising unemployment by ~1 months.
- Opportunities come when markets and liquidity disagree: **Supported**. After sell-offs into improving liquidity, stocks returned +8.7% over 6 months (n=9) vs +5.1% on average; after rallies into draining liquidity, +2.4% (n=5). Small samples.
- Central-bank stress and side effects create opportunities: **Partly supported**. 11 stress events; median next-6m stock return +3.3%. Buying stress worked when the Fed responded fast (2019, 2020, 2023), not in 2008.
- Analogues: The 5 closest past months saw stocks +4% (median) over the next 12 months (range -6% to +22%). History rhymes; it does not repeat.

## 5. Scenarios sum to 100 and update consistently
- Tests: `9 passed, 93 deselected in 0.33s`
- Live: {'base': 51.6, 'bull': 12.2, 'bear': 36.2} (model {'base': 51.6, 'bull': 12.2, 'bear': 36.2}); method: log-odds = log(prior) ± weight × average signal score per evidence group (bull +, bear −); normalised, floor 5%, cap 80%. Groups without data contribute nothing.

## 6. Sources, calculations, dates and units
- Data status: {'due': 42, 'fresh': 126, 'stale': 8, 'failed': 36, 'unavailable': 1}. Failed = Tiingo series blocked by an invalid API key (36).
- Unit/date tests: `38 passed, 64 deselected in 0.45s`
- Every displayed metric has source/observation date/frequency/freshness: `1 passed, 101 deselected in 13.47s`

## 7. Dashboard and weekly report use the same data
- Both are rendered from `site/snapshot.json`. Test: `1 passed, 101 deselected in 0.33s`

## 8. Detecting a meaningful liquidity change (2022-03-31 → 2022-06-30, as-of runs)
- Market liquidity: -0.54 (draining) → -1.30 (draining, deteriorating).
- Scenarios: {'base': 55.2, 'bull': 22.1, 'bear': 22.8} → {'base': 34.8, 'bull': 5.0, 'bear': 60.2}.
- Base case probability: 55.2 → 34.8. Driven by liquidity weakening (-1.0), credit weakening (-0.9), consumer weakening (-0.5).
- Bull case probability: 22.1 → 5.0. Driven by liquidity weakening (-1.0), credit weakening (-0.9), consumer weakening (-0.5).
- Bear case probability: 22.8 → 60.2. Driven by liquidity weakening (-1.0), credit weakening (-0.9), consumer weakening (-0.5).
- Cycle: early recovery → contraction. Leading/coincident indicator balance shifted.
- Economy liquidity: adding → neutral. Impulse now 0.09.
- Bank lending: adding, stable → adding, deteriorating. Impulse 1.49 → 0.73.
- Private credit & bonds: neutral, stable → draining, deteriorating. Impulse -0.38 → -1.02.
- Global liquidity: neutral, stable → draining, deteriorating. Impulse -0.45 → -1.38.
- AI investment: neutral, stable → draining, deteriorating. Impulse 0.18 → -0.54.
- Cross-asset: dollar vs global: neutral → confirm. 
- Cross-asset: commodities vs growth: neutral → confirm. 
- Cross-asset: bitcoin vs liquidity: neutral → confirm. 
- Outlook: International equities: Mildly unattractive → Unattractive. Score -0.67 → -1.09.
- Outlook: Growth stocks: Unattractive → Mildly unattractive. Score -1.03 → -0.81.
- Implication (June 2022): favoured Cash (+0.02), Private credit; least Gold (-1.52). What followed: the S&P 500 fell further into October 2022 before recovering.

