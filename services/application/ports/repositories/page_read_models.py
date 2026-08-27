from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from application.dtos.page_dtos import PageResponse


class PageReadModel(ABC):
    @abstractmethod
    async def get_page_by_id(
        self,
        page_id: UUID,
        workspace_id: UUID | None = None,
    ) -> PageResponse | None:
        pass

    @abstractmethod
    async def get_pages_by_id(
        self,
        page_ids: list[UUID],
        workspace_id: UUID | None = None,
    ) -> list[PageResponse]:
        pass

    @abstractmethod
    async def count_pages_with_summaries(self, artifact_id: UUID) -> int:
        """Count pages belonging to an artifact that have a non-empty summary."""

    @abstractmethod
    async def get_pages_by_artifact_ids(
        self,
        artifact_ids: list[UUID],
        workspace_id: UUID | None = None,
    ) -> list[PageResponse]:
        """Return pages belonging to the given artifacts, sorted by index."""

    @abstractmethod
    async def get_pages_for_cser_export(
        self,
        workspace_id: UUID,
        *,
        only_reviewed: bool,
        since: datetime | None,
    ) -> list[dict]:
        """Pages whose compound annotations should go into a training export.

        ``only_reviewed`` (the default for the endpoint) means a human signed
        off: ``human_corrections.compound_mentions`` exists. That includes
        pages corrected to an EMPTY list — a reviewed negative, which the
        detector needs as much as a positive.
        """
