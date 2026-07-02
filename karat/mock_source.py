"""Deterministic synthetic data source.

Generates the five cases data_contract.md requires the mock data to include,
on purpose:

1. CAMP-001 — low CPL + high volume but poor match rate (the classic leaker).
2. CAMP-002 — higher CPL but strong match rate / RPR (looks expensive,
   actually profitable).
3. CAMP-003 — tiny sample with an extreme match rate (proves MIN_LEADS).
4. Every campaign gets a slice of leads submitted within the last 2 days of
   the window (proves LAG_DAYS handling).
5. Unmatched leads draw from all four failure reasons (feeds the why-summary).

Grain 2 is aggregated from the grain-1 leads plus a synthetic per-campaign
cost (leads x target CPL), so the two grains are mutually consistent by
construction.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from karat.datasource import DataSource
from karat.models import CampaignMetrics, Lead, ReasonNotMatched, Window

import random

# Unmatched leads inside the last RECENT_DAYS of the window prove lag
# handling; keep this below any plausible LAG_DAYS config.
RECENT_DAYS = 2
RECENT_SHARE = 0.10

_UNMATCHED_REASONS = [
    ReasonNotMatched.UNVERIFIED,
    ReasonNotMatched.CLIENT_FILTER,
    ReasonNotMatched.AT_CAP,
    ReasonNotMatched.OTHER,
]
_REASON_WEIGHTS = [0.4, 0.3, 0.2, 0.1]


class _CampaignSpec:
    def __init__(
        self,
        campaign_id: str,
        campaign_name: str,
        leads: int,
        match_rate: float,
        cpl: float,
        payout_range: tuple[float, float],
        clicks_per_lead: int,
    ):
        self.campaign_id = campaign_id
        self.campaign_name = campaign_name
        self.leads = leads
        self.match_rate = match_rate
        self.cpl = cpl
        self.payout_range = payout_range
        self.clicks_per_lead = clicks_per_lead


_SPECS = [
    # The leaker: cheap leads, lots of them, almost none match.
    # 400 leads x $12 = $4,800 cost vs ~40 matched x ~$70 = ~$2,800 revenue.
    _CampaignSpec("CAMP-001", "Business Loans - Broad", 400, 0.10, 12.0, (55.0, 85.0), 9),
    # Looks expensive, actually profitable: high CPL, strong match and RPR.
    # 120 leads x $45 = $5,400 cost vs ~78 matched x ~$200 = ~$15,600 revenue.
    _CampaignSpec("CAMP-002", "Business Insurance - Exact", 120, 0.65, 45.0, (150.0, 250.0), 7),
    # Tiny sample, extreme (100%) match rate: MIN_LEADS must catch this.
    _CampaignSpec("CAMP-003", "POS Systems - Brand", 4, 1.00, 75.0, (150.0, 210.0), 6),
]


class MockDataSource(DataSource):
    def __init__(self, seed: int = 42):
        self.seed = seed

    def get_leads(self, window: Window) -> list[Lead]:
        rng = random.Random(self.seed)
        leads: list[Lead] = []
        for spec in _SPECS:
            leads.extend(self._leads_for_campaign(spec, window, rng))
        return leads

    def get_campaign_metrics(self, window: Window) -> list[CampaignMetrics]:
        by_campaign: dict[str, list[Lead]] = {spec.campaign_id: [] for spec in _SPECS}
        for lead in self.get_leads(window):
            by_campaign[lead.campaign_id].append(lead)

        metrics = []
        for spec in _SPECS:
            campaign_leads = by_campaign[spec.campaign_id]
            metrics.append(
                CampaignMetrics(
                    campaign_id=spec.campaign_id,
                    campaign_name=spec.campaign_name,
                    window_start=window.start,
                    window_end=window.end,
                    cost=round(spec.leads * spec.cpl, 2),
                    clicks=spec.leads * spec.clicks_per_lead,
                    leads=len(campaign_leads),
                    matched_leads=sum(1 for l in campaign_leads if l.matched),
                    revenue=round(sum(l.revenue for l in campaign_leads), 2),
                    verified_leads=sum(1 for l in campaign_leads if l.verified),
                )
            )
        return metrics

    def _leads_for_campaign(
        self, spec: _CampaignSpec, window: Window, rng: random.Random
    ) -> list[Lead]:
        n = spec.leads
        n_matched = round(n * spec.match_rate)
        n_recent = max(1, round(n * RECENT_SHARE))

        # Fixed counts, shuffled positions: match rate is exact by
        # construction, ordering is still pseudo-random.
        matched_flags = [True] * n_matched + [False] * (n - n_matched)
        rng.shuffle(matched_flags)

        leads = []
        for i, matched in enumerate(matched_flags):
            if matched:
                reason = ReasonNotMatched.NONE
                revenue = round(rng.uniform(*spec.payout_range), 2)
                verified = True
            else:
                reason = rng.choices(_UNMATCHED_REASONS, weights=_REASON_WEIGHTS)[0]
                revenue = 0.0
                verified = reason is not ReasonNotMatched.UNVERIFIED

            leads.append(
                Lead(
                    lead_id=f"{spec.campaign_id}-L{i:05d}",
                    campaign_id=spec.campaign_id,
                    campaign_name=spec.campaign_name,
                    submit_ts=self._submit_ts(window, rng, recent=i >= n - n_recent),
                    matched=matched,
                    revenue=revenue,
                    verified=verified,
                    reason_not_matched=reason,
                )
            )
        return leads

    @staticmethod
    def _submit_ts(window: Window, rng: random.Random, recent: bool) -> datetime:
        total_days = (window.end - window.start).days
        if recent:
            day_offset = total_days - rng.randint(0, min(RECENT_DAYS, total_days))
        else:
            day_offset = rng.randint(0, max(total_days - RECENT_DAYS - 1, 0))
        seconds = rng.randint(0, 24 * 3600 - 1)
        return datetime.combine(window.start, time.min) + timedelta(
            days=day_offset, seconds=seconds
        )
