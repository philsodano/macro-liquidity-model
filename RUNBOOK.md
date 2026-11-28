# Weekly run — runbook for the scheduled Claude session

Run every week after Thursday's Fed balance sheet (H.4.1) and Friday's data. Takes ~10 minutes.

## 1. Get the repo
- Attach `philsodano/macro-liquidity-model` (push access) and clone it to `/home/user/macro-liquidity-model`.
- Use Python 3.12 or newer (`python3.13` if the default `python` is older): `python3.13 -m pip install --break-system-packages -e .` and run every `python -m macro …` command with that interpreter.

## 2. Refresh, build, test
```bash
python -m macro refresh      # fetches only series that are due (cadence in config/settings.yaml)
python -m macro build        # runs the model → site/snapshot.json, history/conclusions.jsonl, site/index.html
python -m pytest -q          # must pass; if not, stop and report
```
Read the refresh summary. Any `failed` series: note them in the report notes (source down? Tiingo key?). Never invent data.

## 3. Analyst pass (bounded)
Read `site/snapshot.json` → `executive`, `changes`, `liquidity.consolidated`, `scenarios`, `cross_asset`, `research.principles`.
Write `notes/YYYY-MM-DD.md` (date = snapshot `meta.as_of`) using `## <Section name>` headings from the report
(e.g. `## Liquidity Update`). Rules:
- Interpret, don't restate. Each note ≤ 120 words. Say what changed, why, and what it means for the 12–18 month view.
- Separate fact from interpretation; name the indicator and its date for every number you cite.
- Call out conflicting signals instead of forcing one story.

Optional scenario adjustment: append to `history/overrides.json`
`{"date": "YYYY-MM-DD", "deltas": {"bear": 5, "base": -5}, "reason": "…"}` — each delta within ±10pp, deltas sum to 0,
reason required. The model's own probabilities stay visible next to the adjusted ones. Use only for evidence the model
cannot see (e.g. a policy announcement not yet in the data).

## 4. Rebuild and write the report
```bash
python -m macro build && python -m macro report
```

## 5. Save and publish
- `git add -A && git commit -m "data: weekly update YYYY-MM-DD"` then push to `main`.
- Republish the dashboard to its existing private page https://claude.ai/artifact/3d4VEpJQumgSbYMzo9oy3j: read the artifact first,
  then publish `site/index.html` with files `snapshot.json` and `reports.json` from `site/`.
- Reply with: scenario odds and their change, the 3 biggest changes, any failed sources.
