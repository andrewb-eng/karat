"""DataSource abstraction.

All data access goes through this interface. Logic code must depend only on
DataSource, never on a concrete implementation, so swapping MockDataSource
for LookerDataSource / DatalotDataSource later touches nothing downstream.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from karat.models import CampaignMetrics, Lead, Window


class DataSource(ABC):
    @abstractmethod
    def get_leads(self, window: Window) -> list[Lead]:
        """Grain 1: one Lead per submission inside the window."""

    @abstractmethod
    def get_campaign_metrics(self, window: Window) -> list[CampaignMetrics]:
        """Grain 2: one CampaignMetrics per campaign for the window."""


class LookerDataSource(DataSource):
    """Real campaign metrics from Looker. Not available yet."""

    def get_leads(self, window: Window) -> list[Lead]:
        raise NotImplementedError("Looker access is not wired up yet")

    def get_campaign_metrics(self, window: Window) -> list[CampaignMetrics]:
        raise NotImplementedError("Looker access is not wired up yet")


class DatalotDataSource(DataSource):
    """Real lead-level data from Datalot. Not available yet."""

    def get_leads(self, window: Window) -> list[Lead]:
        raise NotImplementedError("Datalot access is not wired up yet")

    def get_campaign_metrics(self, window: Window) -> list[CampaignMetrics]:
        raise NotImplementedError("Datalot access is not wired up yet")
