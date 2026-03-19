from abc import ABC, abstractmethod
from uuid import UUID

from application.dtos.browse_dtos import (
    ArtifactBrowseItemDTO,
    BrowseCategoriesResponse,
    BrowseFoldersResponse,
)


class TagBrowseReadModel(ABC):
    @abstractmethod
    async def get_tag_categories(
        self,
        workspace_id: UUID | None = None,
        limit: int = 5,
        sticky_categories: list[str] | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> BrowseCategoriesResponse:
        pass

    @abstractmethod
    async def get_tag_folders(
        self,
        entity_type: str,
        workspace_id: UUID | None = None,
        parent: str | None = None,
        skip: int = 0,
        limit: int = 50,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> BrowseFoldersResponse:
        pass

    @abstractmethod
    async def get_folder_artifacts(
        self,
        entity_type: str,
        tag_value: str,
        workspace_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> list[ArtifactBrowseItemDTO]:
        pass
