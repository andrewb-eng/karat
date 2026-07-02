"""Hand-built tests for the reason-mix computation."""

from datetime import datetime

import pytest

from karat.models import Lead, ReasonNotMatched
from karat.reasons import compute_reason_mix

TS = datetime(2026, 5, 10, 12, 0)


def unmatched(campaign_id: str, reason: ReasonNotMatched, i: int) -> Lead:
    return Lead(
        lead_id=f"{campaign_id}-U{i:03d}",
        campaign_id=campaign_id,
        campaign_name=f"Campaign {campaign_id}",
        submit_ts=TS,
        matched=False,
        revenue=0.0,
        verified=reason is not ReasonNotMatched.UNVERIFIED,
        reason_not_matched=reason,
    )


def matched(campaign_id: str, i: int) -> Lead:
    return Lead(
        lead_id=f"{campaign_id}-M{i:03d}",
        campaign_id=campaign_id,
        campaign_name=f"Campaign {campaign_id}",
        submit_ts=TS,
        matched=True,
        revenue=100.0,
        verified=True,
        reason_not_matched=ReasonNotMatched.NONE,
    )


def test_shares_exact():
    """{unverified: 6, client_filter: 3, at_cap: 1} -> 0.60 / 0.30 / 0.10."""
    leads = (
        [unmatched("MIX", ReasonNotMatched.UNVERIFIED, i) for i in range(6)]
        + [unmatched("MIX", ReasonNotMatched.CLIENT_FILTER, 10 + i) for i in range(3)]
        + [unmatched("MIX", ReasonNotMatched.AT_CAP, 20)]
        + [matched("MIX", i) for i in range(4)]  # matched leads must not dilute shares
    )
    mix = compute_reason_mix(leads)["MIX"]
    assert mix["unverified"] == pytest.approx(0.60)
    assert mix["client_filter"] == pytest.approx(0.30)
    assert mix["at_cap"] == pytest.approx(0.10)
    assert mix["other"] == pytest.approx(0.0)
    assert sum(mix.values()) == pytest.approx(1.0)


def test_campaigns_kept_separate():
    leads = [
        unmatched("A", ReasonNotMatched.UNVERIFIED, 0),
        unmatched("B", ReasonNotMatched.AT_CAP, 0),
    ]
    mixes = compute_reason_mix(leads)
    assert mixes["A"]["unverified"] == pytest.approx(1.0)
    assert mixes["A"]["at_cap"] == pytest.approx(0.0)
    assert mixes["B"]["at_cap"] == pytest.approx(1.0)


def test_all_matched_campaign_has_zero_mix():
    """A campaign with no unmatched leads still appears, with all-zero shares."""
    mixes = compute_reason_mix([matched("PERFECT", i) for i in range(3)])
    assert mixes["PERFECT"] == {
        "unverified": 0.0,
        "client_filter": 0.0,
        "at_cap": 0.0,
        "other": 0.0,
    }
