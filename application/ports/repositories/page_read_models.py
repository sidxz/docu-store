from abc import ABC, abstractmethod
from uuid import UUID

from application.dtos.page_dtos import PageResponse


class PageReadModel(ABC):
    @abstractmethod
    async def get_page_by_id(self, page_id: UUID) -> PageResponse | None:
        pass
