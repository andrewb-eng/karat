"""Tests for MockDataSource: shape, the five required contract cases, and
grain-1 / grain-2 consistency."""

from datetime import date, datetime, timedelta

import pytest

from karat.mock_source import MockDataSource
from karat.models import CampaignMetrics, Lead, ReasonNotMatched, Window

WINDOW = Window(start=date(2026, 5, 1), end=date(2026, 5, 31))

# Thresholds used only to characterize the synthetic cases; the real
# correction knobs (MIN_LEADS, LAG_DAYS) come later in config.
LAG_DAYS = 7
MIN_LEADS = 10


@pytest.fixture(scope="module")
def source() -> MockDataSource:
    return MockDataSource(seed=42)


@pytest.fixture(scope="module")
def leads(source) -> list[Lead]:
    return source.get_leads(WINDOW)


@pytest.fixture(scope="module")
def metrics(source) -> list[CampaignMetrics]:
    return source.get_campaign_metrics(WINDOW)


def by_id(metrics: list[CampaignMetrics]) -> dict[str, CampaignMetrics]:
    return {m.campaign_id: m for m in metrics}


# ---------------------------------------------------------------- shape


def test_leads_shape(leads):
    assert leads, "mock source returned no leads"
    assert all(isinstance(l, Lead) for l in leads)

    ids = [l.lead_id for l in leads]
    assert len(ids) == len(set(ids)), "lead_id must be unique"

    for l in leads:
        assert WINDOW.start <= l.submit_ts.date() <= WINDOW.end
        if l.matched:
            assert l.reason_not_matched is ReasonNotMatched.NONE
            assert l.revenue > 0
        else:
            assert l.reason_not_matched is not ReasonNotMatched.NONE
            assert l.revenue == 0.0
        if l.reason_not_matched is ReasonNotMatched.UNVERIFIED:
            assert not l.verified


def test_metrics_shape(metrics):
    assert metrics
    assert all(isinstance(m, CampaignMetrics) for m in metrics)

    ids = [m.campaign_id for m in metrics]
    assert len(ids) == len(set(ids)), "one row per campaign per window"

    for m in metrics:
        assert m.window_start == WINDOW.start
        assert m.window_end == WINDOW.end
        assert 0 <= m.matched_leads <= m.leads
        assert 0 <= m.verified_leads <= m.leads
        assert m.cost > 0


def test_deterministic(leads, metrics):
    again = MockDataSource(seed=42)
    assert again.get_leads(WINDOW) == leads
    assert again.get_campaign_metrics(WINDOW) == metrics


# ------------------------------------- the five required contract cases


def test_case_leaker_low_cpl_high_volume_poor_match(metrics):
    """A campaign that looks good up front but loses money."""
    m = by_id(metrics)["CAMP-001"]
    cpl = m.cost / m.leads
    match_rate = m.matched_leads / m.leads
    assert cpl < 20, "leaker must have low CPL"
    assert m.leads >= 300, "leaker must have high volume"
    assert match_rate < 0.20, "leaker must have poor match rate"
    assert m.revenue - m.cost < 0, "leaker must actually lose money"


def test_case_expensive_but_profitable(metrics):
    m = by_id(metrics)
    leaker, good = m["CAMP-001"], m["CAMP-002"]
    assert good.cost / good.leads > leaker.cost / leaker.leads, "higher CPL"
    assert good.matched_leads / good.leads > 0.5, "strong match rate"
    assert good.revenue / good.leads > leaker.revenue / leaker.leads, "stronger RPR"
    assert good.revenue - good.cost > 0, "actually profitable"


def test_case_tiny_sample_extreme_match_rate(metrics):
    m = by_id(metrics)["CAMP-003"]
    assert m.leads < MIN_LEADS, "must be below any sane MIN_LEADS"
    assert m.matched_leads / m.leads == 1.0, "extreme match rate"


def test_case_recent_leads_inside_lag_days(leads):
    """Every campaign must have leads too fresh to count, so LAG_DAYS
    handling has something to exclude."""
    cutoff = datetime.combine(WINDOW.end, datetime.min.time()) - timedelta(days=LAG_DAYS)
    campaigns = {l.campaign_id for l in leads}
    for cid in campaigns:
        recent = [l for l in leads if l.campaign_id == cid and l.submit_ts > cutoff]
        assert recent, f"{cid} has no leads inside LAG_DAYS"


def test_case_reason_mix(leads):
    reasons = {l.reason_not_matched for l in leads if not l.matched}
    assert reasons == {
        ReasonNotMatched.UNVERIFIED,
        ReasonNotMatched.CLIENT_FILTER,
        ReasonNotMatched.AT_CAP,
        ReasonNotMatched.OTHER,
    }, "unmatched leads must cover all four failure reasons"


# ------------------------------------------------ grain-1 <-> grain-2


def test_grain2_aggregates_match_grain1(leads, metrics):
    for m in metrics:
        cl = [l for l in leads if l.campaign_id == m.campaign_id]
        assert m.leads == len(cl)
        assert m.matched_leads == sum(1 for l in cl if l.matched)
        assert m.verified_leads == sum(1 for l in cl if l.verified)
        assert m.revenue == pytest.approx(sum(l.revenue for l in cl), abs=0.01)
        assert m.campaign_name == cl[0].campaign_name

    assert {m.campaign_id for m in metrics} == {l.campaign_id for l in leads}
