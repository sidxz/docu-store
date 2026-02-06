from uuid import UUID

from returns.result import Failure, Result, Success

from application.dtos.artifact_dtos import ArtifactResponse
from application.ports.repositories.artifact_read_models import ArtifactReadModel


class GetArtifactByIdQuery:
    def __init__(self, artifact_read_model: ArtifactReadModel) -> None:
        self.artifact_read_model = artifact_read_model

    async def execute(self, artifact_id: UUID) -> Result[ArtifactResponse, str]:
        try:
            artifact_data = await self.artifact_read_model.get_artifact_by_id(artifact_id)
            if artifact_data is None:
                return Failure(f"Artifact with ID {artifact_id} not found")

            return Success(artifact_data)
        except ValueError as e:
            return Failure(f"Data error: {e!s}")
