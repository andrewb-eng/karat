# Karat — architectural decision log

Every architectural choice gets a short entry (context, decision, why, date) in
the same turn it is made. Newest entries at the bottom.

## 1. Mock-data-first behind a DataSource interface
- **Context:** Real Looker/Datalot access is not available yet, but the logic needs building now.
- **Decision:** All data access goes through an abstract `DataSource` (`karat/datasource.py`). `MockDataSource` generates deterministic synthetic data in the exact shape of `data_contract.md`; `LookerDataSource` / `DatalotDataSource` are stubs to be filled in later.
- **Why:** Swapping in real sources later must not touch the analysis logic; the contract is the interface.
- **Date:** 2026-07-02

## 2. Recommend-only
- **Context:** Karat evaluates live paid-search campaigns.
- **Decision:** Karat never changes campaigns or pushes anything anywhere. Output is a ranked list plus a written "why."
- **Why:** Keeps the tool safe to run anytime; humans stay in the loop on spend decisions.
- **Date:** 2026-07-02

## 3. Cost rule: plain-Python analysis, LLM only for the why-summary
- **Context:** Runs should cost cents, not dollars.
- **Decision:** The join, profit math, corrections, and flags are plain Python. The LLM (Haiku 4.5 at runtime) only writes the short plain-English summary from an already-computed summary table, never from raw rows.
- **Why:** Deterministic, testable math; tiny token bill.
- **Date:** 2026-07-02

## 4. Lag handling: judge only the mature cohort
- **Context:** Leads need time to sell; recent leads look unmatched even when the campaign is fine.
- **Decision:** Quality and profit are computed only on leads older than `LAG_DAYS` relative to window end. Cost is scaled to that cohort (CPL × mature leads). Leads inside the lag window are returned separately as `pending_leads` and never count against a campaign's match rate or profit.
- **Why:** Prevents punishing campaigns for leads that haven't had time to mature.
- **Date:** 2026-07-02

## 5. Small-sample handling: MIN_LEADS floor + Wilson interval
- **Context:** Tiny campaigns produce extreme match rates by chance.
- **Decision:** Campaigns with fewer than `MIN_LEADS` (mature) leads are flagged `low_confidence` and excluded from the leaking ranking. A Wilson score confidence interval on match rate is reported alongside the point estimate. Bayesian shrinkage toward a global prior is noted as a possible v2.
- **Why:** A hard floor is simple and explainable; the Wilson interval communicates uncertainty without a prior.
- **Date:** 2026-07-02

## 6. Default correction knobs
- **Context:** The contract leaves MIN_LEADS and LAG_DAYS as tunables.
- **Decision:** `MIN_LEADS = 30`, `LAG_DAYS = 7`, as module constants in `karat/config.py`. Analysis functions take them as parameters defaulting to these constants.
- **Why:** 30 is a common small-sample rule of thumb; 7 days covers the typical sell cycle. Parameter defaults keep functions testable and the knobs tunable without touching logic.
- **Date:** 2026-07-02

## 7. Leaking rule mechanics
- **Context:** "Bottom quartile on match rate" needs a concrete definition to be testable.
- **Decision:** The quartile threshold is the inclusive (numpy-linear) Q1 of match rates across *ranked* campaigns — those not low-confidence. A campaign leaks when it is ranked AND (mature profit < 0 OR match_rate ≤ Q1). The quartile branch is skipped when fewer than 2 campaigns are ranked. The whole rule lives in one function, `is_leaking` in `karat/metrics.py`.
- **Why:** Inclusive quantiles behave sensibly at small campaign counts; `≤` guarantees the worst campaign is always caught; low-confidence campaigns must not distort the distribution they are excluded from.
- **Date:** 2026-07-02

## 8. Metrics conventions
- **Context:** Edge cases in `compute_campaign_stats` need consistent handling.
- **Decision:** `low_confidence` is judged on the MATURE lead count (that is the sample actually being scored). Rates are `None` — not 0 — when the mature cohort is empty. CPL uses full window cost / total leads; mature cost = CPL × mature leads. Wilson interval uses z = 1.96 (95%). Aggregation is plain Python over `list[Lead]`; pandas reserved for later tabular/reporting work.
- **Why:** `None` distinguishes "unknowable" from "zero"; judging confidence on the scored cohort avoids trusting a campaign whose volume is all pending; plain Python keeps this layer dependency-light and easily unit-tested.
- **Date:** 2026-07-02

## 9. Leaking severity is two tiers
- **Context:** The single `leaking` flag lumped money-losers together with profitable-but-weak campaigns, which overstates the problem for the latter.
- **Decision:** Tier 1 "losing money" (mature profit < 0) is the real leak. Tier 2 "underperforming" (profitable but bottom-quartile match rate) is a watch/opportunity list, kept separate so profitable campaigns are never labeled leaking. In code: `CampaignStats.leaking` now means Tier 1 only; a new `underperforming` flag means Tier 2; both come from one `leak_tier` function in `karat/metrics.py`. The report layer (`karat/report.py`) additionally filters by profit sign, so a money-loser can never appear in Tier 2 nor a profitable campaign in Tier 1. Tier 1 ranks by dollars lost (biggest first); Tier 2 ranks by match rate ascending.
- **Why:** "Leaking" is an accusation with budget consequences; reserving it for campaigns that verifiably lose money keeps the report trustworthy.
- **Date:** 2026-07-02

## 10. Narration layer
- **Context:** First LLM integration; the cost rule caps it at prose-writing only.
- **Decision:** A `Narrator` interface in `karat/narrate.py` with `narrate(report) -> str`. Its only input is the computed `Report` object (aggregates + reason mix) — never raw leads. `AnthropicNarrator` uses model `claude-haiku-4-5` via the official SDK (imported lazily so tests need no network or SDK), reading `ANTHROPIC_API_KEY` from `.env` via a tiny in-repo parser (no python-dotenv dependency). `FakeNarrator` returns deterministic text from the same report and is the default in the CLI; the live API runs only behind an explicit `--live` flag.
- **Why:** Keeps runs at cents (short JSON summary in, ~2 sentences per campaign out), keeps tests offline, and keeps the LLM swappable/removable without touching math or report code.
- **Date:** 2026-07-02
