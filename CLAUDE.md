# Karat — build rules for Claude Code

Karat ranks business.com paid-search campaigns by real downstream profit (not front-end cost per lead) and explains why leads fail to match. Read `data_contract.md` before writing code.

## How we build
- Incremental. One component at a time. Do not scaffold the whole app in one shot.
- Test as you go. Every math function gets unit tests with hand-computed expected values before we move on.
- Mock-data-first. Build everything against a synthetic data source. Real Looker/Datalot access is not available yet.
- Provider-abstracted. All data access goes through a `DataSource` interface. `MockDataSource` now; `LookerDataSource` / `DatalotDataSource` later. Swapping sources must not touch the logic.
- Recommend-only. Karat never changes campaigns or pushes anything. It outputs a ranked list and a written why.

## Cost rules (important)
- The heavy analysis (join, profit, corrections, flags) is plain Python. No LLM.
- The LLM is used ONLY to write the short plain-English "why" summary, reading an already-computed summary table, not raw rows. Target cents per run. Runtime model: Haiku 4.5.

## Security
- No secrets in the repo. Looker/Datalot/Anthropic keys live in `.env` (gitignored).
- No real client or lead data in the repo. Synthetic data only for tests and demo.

## Stack
- Python. VS Code. Standard libs: pandas for the tables, pytest for tests, pydantic (or dataclasses) for the data models. Keep dependencies minimal.

## Definitions (align with Looker later, do not drift)
- match_rate = matched_leads / leads
- CPL = cost / leads
- RPR = revenue / leads
- profit = revenue - cost
- A campaign is "leaking" if it looks good up front (low CPL, high lead volume) but ranks poorly on profit or match rate, above the small-sample and lag thresholds.
