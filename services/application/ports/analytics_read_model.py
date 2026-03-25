"""Port for analytics aggregation queries."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from application.dtos.stats_dtos import (
    ChatLatencyStatsResponse,
    CitationFrequencyResponse,
    GroundingStatsResponse,
    KnowledgeGapsResponse,
    SearchQualityStatsResponse,
    TokenUsageStatsResponse,
)


class AnalyticsReadModel(Protocol):
    """Read-only queries for analytics aggregation dashboards."""

    async def get_token_usage(
        self, period_days: int, *, workspace_id: UUID | None = None,
    ) -> TokenUsageStatsResponse: ...

    async def get_chat_latency(
        self, period_days: int, *, workspace_id: UUID | None = None,
    ) -> ChatLatencyStatsResponse: ...

    async def get_search_quality(
        self, period_days: int, *, workspace_id: UUID | None = None,
    ) -> SearchQualityStatsResponse: ...

    async def get_grounding_stats(
        self, period_days: int, *, workspace_id: UUID | None = None,
    ) -> GroundingStatsResponse: ...

    async def get_knowledge_gaps(
        self, period_days: int, *, workspace_id: UUID | None = None,
    ) -> KnowledgeGapsResponse: ...

    async def get_citation_frequency(
        self, period_days: int, *, workspace_id: UUID | None = None,
    ) -> CitationFrequencyResponse: ...
