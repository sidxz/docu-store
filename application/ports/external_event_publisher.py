from abc import ABC, abstractmethod
from uuid import UUID

from application.dtos.artifact_dtos import ArtifactResponse
from application.dtos.page_dtos import PageResponse


class ExternalEventPublisher(ABC):
    """Port for publishing domain events to external event streaming services like Kafka."""

    @abstractmethod
    async def notify_page_created(self, page: PageResponse) -> None:
        """Notify that a new page has been created.

        Args:
            page: PageResponse object containing the created page details

        """

    @abstractmethod
    async def notify_page_updated(self, page: PageResponse) -> None:
        """Notify that a page has been updated.

        Args:
            page: PageResponse object containing the updated page details

        """

    @abstractmethod
    async def notify_page_deleted(self, page_id: UUID) -> None:
        """Notify that a page has been deleted.

        Args:
            page_id: UUID of the deleted page

        """

    @abstractmethod
    async def notify_artifact_created(self, artifact: ArtifactResponse) -> None:
        """Notify that a new artifact has been created.

        Args:
            artifact: ArtifactResponse object containing the created artifact details

        """

    @abstractmethod
    async def notify_artifact_updated(self, artifact: ArtifactResponse) -> None:
        """Notify that an artifact has been updated.

        Args:
            artifact: ArtifactResponse object containing the updated artifact details

        """

    @abstractmethod
    async def notify_artifact_deleted(self, artifact_id: UUID) -> None:
        """Notify that an artifact has been deleted.

        Args:
            artifact_id: UUID of the deleted artifact

        """
