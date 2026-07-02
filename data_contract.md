# Karat — data contract

This is the interface between real data (Looker + Datalot) and Karat's logic. The mock source produces data in exactly this shape; the real sources will map into it later. Align field names and definitions with Looker when access lands; do not silently drift.

## Grain 1: lead-level (from Datalot, or synthetic)
One row per lead submission. This is what powers the "why leads didn't match" summary.

| field | type | notes |
|---|---|---|
| lead_id | str | unique |
| campaign_id | str | joins to campaign metrics |
| campaign_name | str | human readable |
| submit_ts | datetime | when the lead came in (drives lag handling) |
| matched | bool | did it match to a paying client |
| revenue | float | client payment if matched, else 0 |
| verified | bool | passed verification |
| reason_not_matched | enum | one of: unverified, client_filter, at_cap, other, none (none = matched) |

## Grain 2: campaign metrics (from Looker, or aggregated from grain 1 + ad spend)
One row per campaign per time window. This is what powers the profit ranking.

| field | type | notes |
|---|---|---|
| campaign_id | str | |
| campaign_name | str | |
| window_start / window_end | date | the period |
| cost | float | ad spend (Looker, sourced from Google Ads) |
| clicks | int | optional |
| leads | int | front-end conversions / form submits |
| matched_leads | int | count matched |
| revenue | float | sum of client payments |
| verified_leads | int | count verified |

## Derived metrics (computed, not stored)
- match_rate = matched_leads / leads
- verified_rate = verified_leads / leads
- CPL = cost / leads
- RPR = revenue / leads
- profit = revenue - cost
- reason mix = share of unmatched leads by reason_not_matched (from grain 1)

## Correction knobs (config, tune later)
- MIN_LEADS: campaigns below this lead count are flagged "low confidence," not ranked as leaking.
- LAG_DAYS: leads newer than this many days are excluded from revenue/match calcs (not enough time to sell). Immature cohorts are reported separately, not counted against the campaign.

## Mock data should include, on purpose
- A campaign with low CPL + high volume but poor match rate (the classic leaker Karat must catch).
- A campaign with higher CPL but strong match/RPR (looks expensive, actually profitable).
- A tiny-sample campaign (few leads, extreme match rate) to prove MIN_LEADS works.
- Recent leads inside LAG_DAYS to prove lag handling works.
- A mix of reason_not_matched values so the why-summary has something to summarize.
