from abc import ABC, abstractmethod

from application.dtos.page_dtos import PageResponse


class ExternalEventPublisher(ABC):
    """Port for publishing domain events to external event streaming services like Kafka."""

    @abstractmethod
    async def notify_page_created(self, page: PageResponse) -> None:
        """Notify that a new page has been created.

        Args:
            page: PageResponse object containing the created page details

        """
