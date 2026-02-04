from uuid import UUID

import structlog
from returns.result import Failure, Result, Success

from application.dtos.artifact_dtos import ArtifactResponse, CreateArtifactRequest
from application.dtos.errors import AppError
from application.mappers.artifact_mappers import ArtifactMapper
from application.ports.external_event_publisher import ExternalEventPublisher
from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.repositories.page_repository import PageRepository
from domain.aggregates.artifact import Artifact
from domain.exceptions import (
    AggregateNotFoundError,
    ConcurrencyError,
    ValidationError,
)
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.title_mention import TitleMention

logger = structlog.get_logger()


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


class AddPagesUseCase:
    """Add pages to an artifact."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    async def execute(
        self,
        artifact_id: UUID,
        page_ids: list[UUID],
    ) -> Result[ArtifactResponse, AppError]:
        try:
            # Retrieve the artifact by ID
            artifact = self.artifact_repository.get_by_id(artifact_id)

            # Validate that all page IDs exist and their artifact_id matches
            for page_id in page_ids:
                page = self.page_repository.get_by_id(page_id)
                if page.artifact_id != artifact_id:
                    return Failure(
                        AppError(
                            "validation",
                            f"Page {page_id} does not belong to Artifact {artifact_id}",
                        ),
                    )

            # Add pages to the artifact
            artifact.add_pages(page_ids)

            # Save the updated artifact
            self.artifact_repository.save(artifact)

            # Return a successful result with the updated ArtifactResponse
            result = ArtifactMapper.to_artifact_response(artifact)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_artifact_updated(result)

            return Success(result)
        except AggregateNotFoundError as e:
            return Failure(AppError("not_found", f"Artifact not found: {e!s}"))
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except ValueError as e:
            return Failure(AppError("invalid_operation", str(e)))


class RemovePagesUseCase:
    """Remove pages from an artifact."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    async def execute(
        self,
        artifact_id: UUID,
        page_ids: list[UUID],
    ) -> Result[ArtifactResponse, AppError]:
        try:
            # Retrieve the artifact by ID
            artifact = self.artifact_repository.get_by_id(artifact_id)

            # Remove pages from the artifact
            artifact.remove_pages(page_ids)

            # Save the updated artifact
            self.artifact_repository.save(artifact)

            # Return a successful result with the updated ArtifactResponse
            result = ArtifactMapper.to_artifact_response(artifact)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_artifact_updated(result)

            return Success(result)
        except AggregateNotFoundError as e:
            return Failure(AppError("not_found", f"Artifact not found: {e!s}"))
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except ValueError as e:
            return Failure(AppError("invalid_operation", str(e)))


class UpdateTitleMentionUseCase:
    """Update title mention for an artifact."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    async def execute(
        self,
        artifact_id: UUID,
        title_mention: TitleMention | None,
    ) -> Result[ArtifactResponse, AppError]:
        try:
            logger.info(
                "update_title_mention_use_case_start",
                artifact_id=str(artifact_id),
                title_mention=title_mention,
                title_mention_type=type(title_mention).__name__ if title_mention else "None",
            )
            # Retrieve the artifact by ID
            logger.info("retrieving_artifact", artifact_id=str(artifact_id))
            artifact = self.artifact_repository.get_by_id(artifact_id)
            logger.info("artifact_retrieved", artifact_id=str(artifact_id))

            # Update title mention
            logger.info(
                "updating_title_mention",
                artifact_id=str(artifact_id),
                title_mention=title_mention,
            )
            artifact.update_title_mention(title_mention)
            logger.info("title_mention_updated", artifact_id=str(artifact_id))

            # Save the updated artifact
            logger.info("saving_artifact", artifact_id=str(artifact_id))
            self.artifact_repository.save(artifact)
            logger.info("artifact_saved", artifact_id=str(artifact_id))

            # Return a successful result with the updated ArtifactResponse
            logger.info("mapping_to_response", artifact_id=str(artifact_id))
            result = ArtifactMapper.to_artifact_response(artifact)
            logger.info("response_mapped", artifact_id=str(artifact_id))

            if self.external_event_publisher:
                logger.info("publishing_event", artifact_id=str(artifact_id))
                await self.external_event_publisher.notify_artifact_updated(result)
                logger.info("event_published", artifact_id=str(artifact_id))

            logger.info("update_title_mention_use_case_success", artifact_id=str(artifact_id))
            return Success(result)
        except AggregateNotFoundError as e:
            logger.warning("artifact_not_found", artifact_id=str(artifact_id), error=str(e))
            return Failure(AppError("not_found", f"Artifact not found: {e!s}"))
        except ValidationError as e:
            logger.warning("validation_error", artifact_id=str(artifact_id), error=str(e))
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            logger.warning("concurrency_error", artifact_id=str(artifact_id), error=str(e))
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except ValueError as e:
            logger.warning("value_error", artifact_id=str(artifact_id), error=str(e))
            return Failure(AppError("invalid_operation", str(e)))
        except Exception as e:
            logger.error(
                "unexpected_error_in_update_title_mention_use_case",
                artifact_id=str(artifact_id),
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))


class UpdateSummaryCandidateUseCase:
    """Update summary candidate for an artifact."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    async def execute(
        self,
        artifact_id: UUID,
        summary_candidate: SummaryCandidate | None,
    ) -> Result[ArtifactResponse, AppError]:
        try:
            # Retrieve the artifact by ID
            artifact = self.artifact_repository.get_by_id(artifact_id)

            # Update summary candidate
            artifact.update_summary_candidate(summary_candidate)

            # Save the updated artifact
            self.artifact_repository.save(artifact)

            # Return a successful result with the updated ArtifactResponse
            result = ArtifactMapper.to_artifact_response(artifact)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_artifact_updated(result)

            return Success(result)
        except AggregateNotFoundError as e:
            return Failure(AppError("not_found", f"Artifact not found: {e!s}"))
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except ValueError as e:
            return Failure(AppError("invalid_operation", str(e)))


class UpdateTagsUseCase:
    """Update tags for an artifact."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    async def execute(
        self,
        artifact_id: UUID,
        tags: list[str],
    ) -> Result[ArtifactResponse, AppError]:
        try:
            # Retrieve the artifact by ID
            artifact = self.artifact_repository.get_by_id(artifact_id)

            # Update tags
            artifact.update_tags(tags)

            # Save the updated artifact
            self.artifact_repository.save(artifact)

            # Return a successful result with the updated ArtifactResponse
            result = ArtifactMapper.to_artifact_response(artifact)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_artifact_updated(result)

            return Success(result)
        except AggregateNotFoundError as e:
            return Failure(AppError("not_found", f"Artifact not found: {e!s}"))
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except ValueError as e:
            return Failure(AppError("invalid_operation", str(e)))


class DeleteArtifactUseCase:
    """Delete an artifact and all its associated pages."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    async def execute(self, artifact_id: UUID) -> Result[None, AppError]:
        try:
            # Retrieve the artifact and its pages
            artifact = self.artifact_repository.get_by_id(artifact_id)
            pages = [self.page_repository.get_by_id(page_id) for page_id in artifact.pages]

            # Use the domain service to delete artifact and all its pages
            from domain.services.artifact_deletion_service import ArtifactDeletionService

            ArtifactDeletionService.delete_artifact_with_pages(artifact, pages)

            # Persist all deleted aggregates
            for page in pages:
                self.page_repository.save(page)
            self.artifact_repository.save(artifact)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_artifact_deleted(artifact_id)

            # Return a successful result
            return Success(None)
        except AggregateNotFoundError as e:
            return Failure(AppError("not_found", f"Artifact not found: {e!s}"))
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except ValueError as e:
            return Failure(AppError("invalid_operation", str(e)))
