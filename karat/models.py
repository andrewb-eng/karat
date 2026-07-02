"""Pydantic models for the two grains defined in data_contract.md.

Field names and definitions must stay aligned with the contract (and later
with Looker). Do not rename or redefine fields here without updating the
contract first.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, model_validator


class ReasonNotMatched(str, Enum):
    UNVERIFIED = "unverified"
    CLIENT_FILTER = "client_filter"
    AT_CAP = "at_cap"
    OTHER = "other"
    NONE = "none"  # none = matched


class Window(BaseModel):
    """A reporting period. Both endpoints inclusive."""

    start: date
    end: date

    @model_validator(mode="after")
    def _check_order(self) -> "Window":
        if self.end < self.start:
            raise ValueError("window end must not be before start")
        return self


class Lead(BaseModel):
    """Grain 1: one row per lead submission (Datalot, or synthetic)."""

    lead_id: str
    campaign_id: str
    campaign_name: str
    submit_ts: datetime
    matched: bool
    revenue: float
    verified: bool
    reason_not_matched: ReasonNotMatched

    @model_validator(mode="after")
    def _check_consistency(self) -> "Lead":
        if self.matched and self.reason_not_matched is not ReasonNotMatched.NONE:
            raise ValueError("matched lead must have reason_not_matched = none")
        if not self.matched and self.reason_not_matched is ReasonNotMatched.NONE:
            raise ValueError("unmatched lead must have a reason_not_matched")
        if not self.matched and self.revenue != 0:
            raise ValueError("unmatched lead must have revenue = 0")
        if self.revenue < 0:
            raise ValueError("revenue must be >= 0")
        return self


class CampaignMetrics(BaseModel):
    """Grain 2: one row per campaign per time window (Looker, or aggregated)."""

    campaign_id: str
    campaign_name: str
    window_start: date
    window_end: date
    cost: float
    clicks: int | None = None
    leads: int
    matched_leads: int
    revenue: float
    verified_leads: int

    @model_validator(mode="after")
    def _check_counts(self) -> "CampaignMetrics":
        if self.matched_leads > self.leads:
            raise ValueError("matched_leads cannot exceed leads")
        if self.verified_leads > self.leads:
            raise ValueError("verified_leads cannot exceed leads")
        if min(self.cost, self.revenue, self.leads, self.matched_leads, self.verified_leads) < 0:
            raise ValueError("counts and money fields must be >= 0")
        return self
