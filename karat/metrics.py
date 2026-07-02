"""Per-campaign analysis math. Plain Python only — no LLM here (cost rules
in CLAUDE.md).

Definitions follow data_contract.md exactly (match_rate = matched/leads,
CPL = cost/leads, RPR = revenue/leads, profit = revenue - cost), with one
correction: quality and profit are evaluated on the MATURE cohort only —
leads submitted more than lag_days before window end. Cost is scaled to that
cohort (CPL x mature leads); pending leads are counted separately and never
affect match_rate or profit.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import sqrt

from pydantic import BaseModel

from karat.config import LAG_DAYS, MIN_LEADS
from karat.models import Lead, Window

Z_95 = 1.96


class CampaignStats(BaseModel):
    """Enriched per-campaign result for one window. Counts, revenue, and
    profit refer to the mature cohort; `leads` and `cost` are window totals."""

    campaign_id: str
    campaign_name: str
    window_start: date
    window_end: date
    leads: int
    mature_leads: int
    pending_leads: int
    matched_leads: int
    verified_leads: int
    cost: float
    mature_cost: float
    revenue: float
    match_rate: float | None
    verified_rate: float | None
    cpl: float | None
    rpr: float | None
    profit: float
    match_rate_ci: tuple[float, float] | None
    low_confidence: bool
    leaking: bool  # Tier 1: losing money (mature profit < 0)
    underperforming: bool  # Tier 2: profitable but bottom-quartile match rate


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion (95% by
    default). Returns the maximally uncertain (0, 1) when n = 0."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def leak_tier(s: CampaignStats, bottom_quartile_match_rate: float | None) -> int | None:
    """The leaking rule, in one place — now two tiers (DECISIONS.md #9).

    Requires a trusted mature sample (not low confidence). Then:
    Tier 1 "losing money": mature profit < 0 — the real leak.
    Tier 2 "underperforming": profitable but match rate in the bottom
    quartile of ranked campaigns — a watch/opportunity, never labeled
    leaking.
    Returns 1, 2, or None.
    """
    if s.low_confidence or s.match_rate is None:
        return None
    if s.profit < 0:
        return 1
    if (
        bottom_quartile_match_rate is not None
        and s.match_rate <= bottom_quartile_match_rate
    ):
        return 2
    return None


def compute_campaign_stats(
    leads: list[Lead],
    costs: dict[str, float],
    window: Window,
    min_leads: int = MIN_LEADS,
    lag_days: int = LAG_DAYS,
) -> list[CampaignStats]:
    """Aggregate grain-1 leads + per-campaign ad spend into enriched
    per-campaign stats for the window."""
    maturity_cutoff = datetime.combine(window.end, time.min) - timedelta(days=lag_days)

    by_campaign: dict[str, list[Lead]] = defaultdict(list)
    for lead in leads:
        by_campaign[lead.campaign_id].append(lead)

    stats: list[CampaignStats] = []
    for campaign_id, campaign_leads in sorted(by_campaign.items()):
        mature = [l for l in campaign_leads if l.submit_ts < maturity_cutoff]
        n_total, n_mature = len(campaign_leads), len(mature)
        matched = sum(1 for l in mature if l.matched)
        verified = sum(1 for l in mature if l.verified)
        revenue = sum(l.revenue for l in mature)
        cost = costs.get(campaign_id, 0.0)

        cpl = cost / n_total if n_total else None
        mature_cost = (cpl or 0.0) * n_mature

        stats.append(
            CampaignStats(
                campaign_id=campaign_id,
                campaign_name=campaign_leads[0].campaign_name,
                window_start=window.start,
                window_end=window.end,
                leads=n_total,
                mature_leads=n_mature,
                pending_leads=n_total - n_mature,
                matched_leads=matched,
                verified_leads=verified,
                cost=cost,
                mature_cost=mature_cost,
                revenue=revenue,
                match_rate=matched / n_mature if n_mature else None,
                verified_rate=verified / n_mature if n_mature else None,
                cpl=cpl,
                rpr=revenue / n_mature if n_mature else None,
                profit=revenue - mature_cost,
                match_rate_ci=wilson_interval(matched, n_mature) if n_mature else None,
                low_confidence=n_mature < min_leads,
                leaking=False,  # set below, needs the cross-campaign quartile
                underperforming=False,
            )
        )

    ranked_rates = [
        s.match_rate for s in stats if not s.low_confidence and s.match_rate is not None
    ]
    bottom_quartile = (
        statistics.quantiles(ranked_rates, n=4, method="inclusive")[0]
        if len(ranked_rates) >= 2
        else None
    )
    for s in stats:
        tier = leak_tier(s, bottom_quartile)
        s.leaking = tier == 1
        s.underperforming = tier == 2
    return stats
