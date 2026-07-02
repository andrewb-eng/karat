"""Tests for report tiering, ranking, markdown rendering, and the offline
narrator. No network — FakeNarrator only."""

from datetime import date

import pytest

from karat.metrics import CampaignStats
from karat.models import Window
from karat.narrate import FakeNarrator
from karat.report import build_report, render_markdown

WINDOW = Window(start=date(2026, 5, 1), end=date(2026, 5, 31))


def mk_stats(
    campaign_id: str,
    *,
    profit: float,
    match_rate: float = 0.30,
    leaking: bool = False,
    underperforming: bool = False,
    low_confidence: bool = False,
    leads: int = 100,
) -> CampaignStats:
    cost = 1000.0
    revenue = cost + profit
    return CampaignStats(
        campaign_id=campaign_id,
        campaign_name=f"Campaign {campaign_id}",
        window_start=WINDOW.start,
        window_end=WINDOW.end,
        leads=leads,
        mature_leads=leads,
        pending_leads=0,
        matched_leads=round(leads * match_rate),
        verified_leads=leads,
        cost=cost,
        mature_cost=cost,
        revenue=revenue,
        match_rate=match_rate,
        verified_rate=1.0,
        cpl=cost / leads,
        rpr=revenue / leads,
        profit=profit,
        match_rate_ci=(max(0.0, match_rate - 0.1), min(1.0, match_rate + 0.1)),
        low_confidence=low_confidence,
        leaking=leaking,
        underperforming=underperforming,
    )


ZERO_MIX = {"unverified": 0.0, "client_filter": 0.0, "at_cap": 0.0, "other": 0.0}


def test_tier1_ranked_by_dollars_lost_biggest_first():
    stats = [
        mk_stats("T1-A", profit=-500.0, leaking=True),
        mk_stats("T1-B", profit=-2000.0, leaking=True),
        mk_stats("T1-C", profit=-100.0, leaking=True),
    ]
    report = build_report(stats, {}, WINDOW)
    assert [e.profit for e in report.tier1] == [-2000.0, -500.0, -100.0]


def test_tier2_ranked_by_match_rate_ascending():
    stats = [
        mk_stats("T2-A", profit=300.0, match_rate=0.25, underperforming=True),
        mk_stats("T2-B", profit=300.0, match_rate=0.10, underperforming=True),
    ]
    report = build_report(stats, {}, WINDOW)
    assert [e.campaign_id for e in report.tier2] == ["T2-B", "T2-A"]


def test_tier_invariants():
    """Tier 2 never contains a money loser; Tier 1 never a profitable campaign."""
    stats = [
        mk_stats("LOSER", profit=-2000.0, match_rate=0.10, leaking=True),
        mk_stats("WATCH", profit=300.0, match_rate=0.15, underperforming=True),
        mk_stats("OK", profit=5000.0, match_rate=0.60),
        mk_stats("TINY", profit=100.0, match_rate=1.0, low_confidence=True, leads=4),
        # Defensive: inconsistent flags must not break the invariant.
        mk_stats("WEIRD", profit=-50.0, underperforming=True),
    ]
    report = build_report(stats, {}, WINDOW)

    assert all(e.profit < 0 for e in report.tier1)
    assert all(e.profit >= 0 for e in report.tier2)
    tier1_ids = {e.campaign_id for e in report.tier1}
    tier2_ids = {e.campaign_id for e in report.tier2}
    assert not tier1_ids & tier2_ids
    assert "WEIRD" not in tier2_ids  # money loser, whatever the flag says
    assert "TINY" in {e.campaign_id for e in report.low_confidence}
    assert "OK" in {e.campaign_id for e in report.healthy}


def test_full_pipeline_tier_invariants():
    """Mock source -> metrics -> report keeps the tier invariants."""
    from karat.metrics import compute_campaign_stats
    from karat.mock_source import MockDataSource
    from karat.reasons import compute_reason_mix

    source = MockDataSource(seed=42)
    leads = source.get_leads(WINDOW)
    costs = {m.campaign_id: m.cost for m in source.get_campaign_metrics(WINDOW)}
    stats = compute_campaign_stats(leads, costs, WINDOW)
    report = build_report(stats, compute_reason_mix(leads), WINDOW)

    assert all(e.profit < 0 for e in report.tier1)
    assert all(e.profit >= 0 for e in report.tier2)
    assert "CAMP-001" in {e.campaign_id for e in report.tier1}  # the designed leaker


def test_rendered_report_contains_actual_numbers():
    stats = [
        mk_stats("T1-B", profit=-2000.0, match_rate=0.10, leaking=True),
        mk_stats("T2-A", profit=300.0, match_rate=0.25, underperforming=True),
    ]
    mixes = {"T1-B": {**ZERO_MIX, "unverified": 0.7, "client_filter": 0.3}}
    report = build_report(stats, mixes, WINDOW)
    narrative = FakeNarrator().narrate(report)
    md = render_markdown(report, narrative)

    assert "$2,000.00" in md  # the actual dollars lost
    assert "10.0%" in md  # T1-B match rate
    assert "25.0%" in md  # T2-A match rate
    assert "Campaign T1-B" in md
    assert "Campaign T2-A" in md
    assert "unverified" in md  # top reason from the mix
    assert narrative in md  # the narrator's text made it into the report


def test_fake_narrator_is_deterministic_and_grounded():
    stats = [mk_stats("T1-B", profit=-2000.0, match_rate=0.10, leaking=True)]
    report = build_report(stats, {"T1-B": {**ZERO_MIX, "at_cap": 1.0}}, WINDOW)
    narrator = FakeNarrator()
    first, second = narrator.narrate(report), narrator.narrate(report)
    assert first == second
    assert "Campaign T1-B" in first
    assert "$2,000.00" in first  # states the money lost
    assert "at_cap" in first  # states the top reason


def test_fake_narrator_empty_report():
    report = build_report([mk_stats("OK", profit=500.0, match_rate=0.6)], {}, WINDOW)
    text = FakeNarrator().narrate(report)
    assert isinstance(text, str) and text  # deterministic non-empty fallback
