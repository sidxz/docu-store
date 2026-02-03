from returns.result import Failure, Result, Success

from application.dtos.artifact_dtos import ArtifactResponse, CreateArtifactRequest
from application.dtos.errors import AppError
from application.mappers.artifact_mappers import ArtifactMapper
from application.ports.external_event_publisher import ExternalEventPublisher
from application.ports.repositories.artifact_repository import ArtifactRepository
from domain.aggregates.artifact import Artifact
from domain.exceptions import (
    ConcurrencyError,
    ValidationError,
)


class CreateArtifactUseCase:
    """Create a new artifact."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    async def execute(self, request: CreateArtifactRequest) -> Result[ArtifactResponse, AppError]:
        try:
            # Create a new Artifact aggregate
            artifact = Artifact.create(
                source_uri=request.source_uri,
                source_filename=request.source_filename,
                artifact_type=request.artifact_type,
                mime_type=request.mime_type,
                storage_location=request.storage_location,
            )

            # Save the Artifact using the repository
            self.artifact_repository.save(artifact)

            result = ArtifactMapper.to_artifact_response(artifact)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_artifact_created(result)

            # Return a successful result with the ArtifactResponse
            return Success(result)
        except ValidationError as e:
            # Domain validation errors - client's fault (400 Bad Request)
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            # Concurrency conflicts (409 Conflict)
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
