from abc import ABC, abstractmethod
from uuid import UUID


class TagDictionaryReadModel(ABC):
    @abstractmethod
    async def suggest_tags(
        self,
        query: str,
        workspace_id: UUID | None = None,
        limit: int = 10,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> list[dict[str, str]]:
        pass


    @abstractmethod
    async def get_popular_tags(
        self,
        workspace_id: UUID | None = None,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        pass

    @abstractmethod
    async def get_category_stats(
        self,
        workspace_id: UUID | None = None,
    ) -> list[dict]:
        pass
