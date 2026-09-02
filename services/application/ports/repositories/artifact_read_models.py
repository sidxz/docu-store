from abc import ABC, abstractmethod
from uuid import UUID

from application.dtos.artifact_dtos import ArtifactResponse


class ArtifactReadModel(ABC):
    @abstractmethod
    async def get_artifact_by_id(
        self,
        artifact_id: UUID,
        workspace_id: UUID | None = None,
    ) -> ArtifactResponse | None:
        pass

    @abstractmethod
    async def find_artifact_id_by_source_uri(
        self,
        source_uri: str,
        workspace_id: UUID | None = None,
    ) -> UUID | None:
        """The artifact already holding this source, if any.

        Returns the id alone rather than the artifact: the only caller asks in
        order to decide whether to fetch and ingest, and hydrating pages to
        answer a yes/no question is work nobody wants done.
        """

    @abstractmethod
    async def list_artifacts(
        self,
        workspace_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
        allowed_artifact_ids: list[UUID] | None = None,
        sort_by: str = "updated_at",
        sort_order: int = -1,
    ) -> list[ArtifactResponse]:
        pass
