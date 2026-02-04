from abc import ABC, abstractmethod
from uuid import UUID

from application.dtos.artifact_dtos import ArtifactResponse


class ArtifactReadModel(ABC):
    @abstractmethod
    async def get_artifact_by_id(self, artifact_id: UUID) -> ArtifactResponse | None:
        pass

    @abstractmethod
    async def list_artifacts(self, skip: int = 0, limit: int = 100) -> list[ArtifactResponse]:
        pass
