"""Ranked output: split CampaignStats into severity tiers (DECISIONS.md #9)
and render a markdown report. Plain Python — no LLM here; the narrative
string is produced elsewhere and passed in."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from karat.metrics import CampaignStats
from karat.models import Window

_ZERO_MIX = {"unverified": 0.0, "client_filter": 0.0, "at_cap": 0.0, "other": 0.0}


def fmt_money(x: float) -> str:
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def fmt_pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


class ReportEntry(BaseModel):
    campaign_id: str
    campaign_name: str
    leads: int
    mature_leads: int
    pending_leads: int
    match_rate: float | None
    match_rate_ci: tuple[float, float] | None
    cpl: float | None
    rpr: float | None
    cost: float
    mature_cost: float
    revenue: float
    profit: float
    reason_mix: dict[str, float]

    def top_reason(self) -> str | None:
        """The most common reason this campaign's leads didn't match."""
        if not any(self.reason_mix.values()):
            return None
        return max(self.reason_mix, key=lambda r: self.reason_mix[r])


class Report(BaseModel):
    window_start: date
    window_end: date
    tier1: list[ReportEntry]  # losing money — ranked by dollars lost, biggest first
    tier2: list[ReportEntry]  # underperforming — ranked by match rate ascending
    low_confidence: list[ReportEntry]  # below MIN_LEADS, excluded from ranking
    healthy: list[ReportEntry]


def build_report(
    stats: list[CampaignStats],
    reason_mixes: dict[str, dict[str, float]],
    window: Window,
) -> Report:
    def entry(s: CampaignStats) -> ReportEntry:
        return ReportEntry(
            campaign_id=s.campaign_id,
            campaign_name=s.campaign_name,
            leads=s.leads,
            mature_leads=s.mature_leads,
            pending_leads=s.pending_leads,
            match_rate=s.match_rate,
            match_rate_ci=s.match_rate_ci,
            cpl=s.cpl,
            rpr=s.rpr,
            cost=s.cost,
            mature_cost=s.mature_cost,
            revenue=s.revenue,
            profit=s.profit,
            reason_mix=reason_mixes.get(s.campaign_id, dict(_ZERO_MIX)),
        )

    # The profit-sign filters are deliberate belt-and-suspenders on top of the
    # metrics flags: a money loser can never land in Tier 2, nor a profitable
    # campaign in Tier 1 (DECISIONS.md #9).
    tier1 = sorted((s for s in stats if s.leaking and s.profit < 0), key=lambda s: s.profit)
    tier2 = sorted(
        (s for s in stats if s.underperforming and s.profit >= 0),
        key=lambda s: (s.match_rate is None, s.match_rate),
    )
    flagged = {s.campaign_id for s in tier1} | {s.campaign_id for s in tier2}
    low_confidence = [s for s in stats if s.low_confidence]
    healthy = sorted(
        (
            s
            for s in stats
            if not s.low_confidence and s.campaign_id not in flagged
        ),
        key=lambda s: -s.profit,
    )

    return Report(
        window_start=window.start,
        window_end=window.end,
        tier1=[entry(s) for s in tier1],
        tier2=[entry(s) for s in tier2],
        low_confidence=[entry(s) for s in low_confidence],
        healthy=[entry(s) for s in healthy],
    )


def _table(entries: list[ReportEntry]) -> list[str]:
    lines = [
        "| campaign | profit | match rate (95% CI) | CPL | RPR | leads (pending) | top reason unmatched |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in entries:
        ci = f"{fmt_pct(e.match_rate_ci[0])}–{fmt_pct(e.match_rate_ci[1])}" if e.match_rate_ci else "n/a"
        lines.append(
            f"| {e.campaign_name} ({e.campaign_id}) "
            f"| {fmt_money(e.profit)} "
            f"| {fmt_pct(e.match_rate)} ({ci}) "
            f"| {fmt_money(e.cpl) if e.cpl is not None else 'n/a'} "
            f"| {fmt_money(e.rpr) if e.rpr is not None else 'n/a'} "
            f"| {e.mature_leads} ({e.pending_leads} pending) "
            f"| {e.top_reason() or 'n/a'} |"
        )
    return lines


def render_markdown(report: Report, narrative: str | None = None) -> str:
    out = [f"# Karat report — {report.window_start} to {report.window_end}", ""]

    if narrative:
        out += ["## Why (plain English)", "", narrative, ""]

    out += ["## Tier 1 — losing money (leaking)", ""]
    out += _table(report.tier1) if report.tier1 else ["No campaigns are losing money."]
    out += ["", "## Tier 2 — underperforming (watch, still profitable)", ""]
    out += _table(report.tier2) if report.tier2 else ["No underperforming campaigns."]

    if report.low_confidence:
        out += ["", "## Low confidence (too few mature leads to judge)", ""]
        out += _table(report.low_confidence)
    if report.healthy:
        out += ["", "## Healthy", ""]
        out += _table(report.healthy)

    return "\n".join(out) + "\n"
