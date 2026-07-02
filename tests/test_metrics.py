"""Hand-built fixtures with hand-computed expected values for the analysis
math. Deliberately does NOT use the random mock source (except one smoke test
at the end proving the layers connect)."""

from datetime import date, datetime

import pytest

from karat.metrics import CampaignStats, compute_campaign_stats, wilson_interval
from karat.models import Lead, ReasonNotMatched, Window

WINDOW = Window(start=date(2026, 5, 1), end=date(2026, 5, 31))
# LAG_DAYS = 7, so the maturity cutoff is 2026-05-24 00:00.
MATURE_TS = datetime(2026, 5, 10, 12, 0)
PENDING_TS = datetime(2026, 5, 29, 12, 0)


def make_leads(
    campaign_id: str, n: int, n_matched: int, ts: datetime, revenue_each: float
) -> list[Lead]:
    leads = []
    for i in range(n):
        matched = i < n_matched
        leads.append(
            Lead(
                lead_id=f"{campaign_id}-{ts:%d}-{i:04d}",
                campaign_id=campaign_id,
                campaign_name=f"Campaign {campaign_id}",
                submit_ts=ts,
                matched=matched,
                revenue=revenue_each if matched else 0.0,
                verified=True,
                reason_not_matched=(
                    ReasonNotMatched.NONE if matched else ReasonNotMatched.CLIENT_FILTER
                ),
            )
        )
    return leads


@pytest.fixture(scope="module")
def stats() -> dict[str, CampaignStats]:
    leads = (
        # TEST-A: 100 leads, 40 matched, revenue 4000, cost 1200, all mature.
        make_leads("TEST-A", 100, 40, MATURE_TS, 100.0)
        # TEST-B: 5 leads, 5 matched, revenue 250, cost 60 — tiny sample.
        + make_leads("TEST-B", 5, 5, MATURE_TS, 50.0)
        # TEST-C: 200 leads, 20 matched, revenue 1000, cost 3000 — money loser.
        + make_leads("TEST-C", 200, 20, MATURE_TS, 50.0)
        # TEST-D: 50 mature (20 matched, revenue 2000) + 10 pending (0 matched).
        # Cost 720 over 60 leads -> CPL 12, mature cost 12 * 50 = 600.
        + make_leads("TEST-D", 50, 20, MATURE_TS, 100.0)
        + make_leads("TEST-D", 10, 0, PENDING_TS, 0.0)
    )
    costs = {"TEST-A": 1200.0, "TEST-B": 60.0, "TEST-C": 3000.0, "TEST-D": 720.0}
    return {s.campaign_id: s for s in compute_campaign_stats(leads, costs, WINDOW)}


# ------------------------------------------------------------- wilson


def test_wilson_hand_computed():
    # 40/100 at 95%: center 0.40370, half-width 0.09430 (hand-computed).
    low, high = wilson_interval(40, 100)
    assert low == pytest.approx(0.3094, abs=2e-4)
    assert high == pytest.approx(0.4980, abs=2e-4)


def test_wilson_edges():
    assert wilson_interval(0, 0) == (0.0, 1.0)
    low, high = wilson_interval(5, 5)
    assert 0.0 <= low <= high <= 1.0
    assert high == pytest.approx(1.0)
    assert low < 1.0  # 5/5 must not read as certainty


# ------------------------------------------------------- TEST-A basics


def test_a_basic_metrics(stats):
    a = stats["TEST-A"]
    assert a.leads == 100
    assert a.mature_leads == 100
    assert a.pending_leads == 0
    assert a.match_rate == pytest.approx(0.40)
    assert a.verified_rate == pytest.approx(1.0)
    assert a.cpl == pytest.approx(12.00)
    assert a.rpr == pytest.approx(40.00)
    assert a.profit == pytest.approx(2800.0)
    assert a.low_confidence is False
    assert a.leaking is False  # profitable and healthy match rate
    ci_low, ci_high = a.match_rate_ci
    assert ci_low == pytest.approx(0.3094, abs=2e-4)
    assert ci_high == pytest.approx(0.4980, abs=2e-4)


# ------------------------------------------------- TEST-B small sample


def test_b_low_confidence_excluded_from_leaking(stats):
    b = stats["TEST-B"]
    assert b.leads == 5
    assert b.match_rate == pytest.approx(1.0)
    assert b.low_confidence is True
    assert b.leaking is False  # never ranked as leaking below MIN_LEADS


# ------------------------------------------------------ TEST-C leaker


def test_c_unprofitable_is_leaking(stats):
    c = stats["TEST-C"]
    assert c.profit == pytest.approx(-2000.0)
    assert c.low_confidence is False
    assert c.leaking is True  # Tier 1: losing money
    assert c.underperforming is False  # tiers are mutually exclusive


# --------------------------------------------------------- TEST-D lag


def test_d_lag_mature_cohort_only(stats):
    d = stats["TEST-D"]
    assert d.leads == 60
    assert d.mature_leads == 50
    assert d.pending_leads == 10
    # 20/50 on the mature cohort — NOT 20/60 = 0.33.
    assert d.match_rate == pytest.approx(0.40)
    assert d.cpl == pytest.approx(12.00)  # 720 / 60
    assert d.mature_cost == pytest.approx(600.0)  # 12 * 50
    assert d.profit == pytest.approx(1400.0)  # 2000 - 600
    assert d.leaking is False


# --------------------------- Tier 2: underperforming (bottom quartile)


def test_underperforming_bottom_quartile_despite_profit():
    """All four campaigns are profitable; the worst match rate is flagged
    underperforming (Tier 2) but never leaking — profitable campaigns are
    never labeled leaking."""
    leads = (
        make_leads("Q-1", 40, 4, MATURE_TS, 500.0)  # match rate 0.10, revenue 2000
        + make_leads("Q-2", 40, 16, MATURE_TS, 100.0)  # 0.40
        + make_leads("Q-3", 40, 20, MATURE_TS, 100.0)  # 0.50
        + make_leads("Q-4", 40, 24, MATURE_TS, 100.0)  # 0.60
    )
    costs = {c: 400.0 for c in ("Q-1", "Q-2", "Q-3", "Q-4")}
    by_id = {s.campaign_id: s for s in compute_campaign_stats(leads, costs, WINDOW)}

    assert all(s.profit > 0 for s in by_id.values())
    # Q1 of [0.10, 0.40, 0.50, 0.60] = 0.325 -> only Q-1 is bottom-quartile.
    assert by_id["Q-1"].underperforming is True
    assert by_id["Q-1"].leaking is False  # profitable -> never "leaking"
    for cid in ("Q-2", "Q-3", "Q-4"):
        assert by_id[cid].underperforming is False
        assert by_id[cid].leaking is False


# ------------------------------------------- smoke: layers fit together


def test_smoke_mock_source_through_metrics():
    """The deterministic mock's designed cases survive the analysis math."""
    from karat.mock_source import MockDataSource

    source = MockDataSource(seed=42)
    leads = source.get_leads(WINDOW)
    costs = {m.campaign_id: m.cost for m in source.get_campaign_metrics(WINDOW)}
    by_id = {s.campaign_id: s for s in compute_campaign_stats(leads, costs, WINDOW)}

    assert by_id["CAMP-001"].leaking is True  # the designed leaker (Tier 1)
    assert by_id["CAMP-001"].underperforming is False
    assert by_id["CAMP-002"].leaking is False  # expensive but profitable
    assert by_id["CAMP-002"].profit > 0
    assert by_id["CAMP-003"].low_confidence is True  # tiny sample
    assert by_id["CAMP-003"].leaking is False
