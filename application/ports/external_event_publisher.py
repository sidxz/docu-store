from abc import ABC, abstractmethod

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
    async def notify_artifact_created(self, artifact: ArtifactResponse) -> None:
        """Notify that a new artifact has been created.

        Args:
            artifact: ArtifactResponse object containing the created artifact details

        """
