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
    async def list_artifacts(
        self,
        workspace_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> list[ArtifactResponse]:
        pass
