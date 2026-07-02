"""Reason mix: per campaign, the share of UNMATCHED leads by
reason_not_matched. Pure Python, no LLM — feeds the why-summary."""

from __future__ import annotations

from collections import defaultdict

from karat.models import Lead, ReasonNotMatched

UNMATCHED_REASONS = [
    ReasonNotMatched.UNVERIFIED,
    ReasonNotMatched.CLIENT_FILTER,
    ReasonNotMatched.AT_CAP,
    ReasonNotMatched.OTHER,
]


def compute_reason_mix(leads: list[Lead]) -> dict[str, dict[str, float]]:
    """campaign_id -> {reason: share of that campaign's unmatched leads}.

    Matched leads never enter the denominator. Every campaign present in
    `leads` gets an entry; a campaign with no unmatched leads gets all zeros.
    All four reason keys are always present.
    """
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {r.value: 0 for r in UNMATCHED_REASONS}
    )
    for lead in leads:
        campaign_counts = counts[lead.campaign_id]  # touch so campaign appears
        if not lead.matched:
            campaign_counts[lead.reason_not_matched.value] += 1

    mixes: dict[str, dict[str, float]] = {}
    for campaign_id, campaign_counts in counts.items():
        total_unmatched = sum(campaign_counts.values())
        mixes[campaign_id] = {
            reason: (n / total_unmatched if total_unmatched else 0.0)
            for reason, n in campaign_counts.items()
        }
    return mixes
