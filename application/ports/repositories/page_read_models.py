from abc import ABC, abstractmethod
from uuid import UUID


class PageReadModel(ABC):
    @abstractmethod
    async def get_page_by_id(self, page_id: UUID) -> dict | None:
        pass
