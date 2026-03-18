from __future__ import annotations

from typing import TYPE_CHECKING
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
from domain.services.artifact_deletion_service import ArtifactDeletionService
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.title_mention import TitleMention

from application.ports.blob_store import BlobStore
from application.ports.compound_vector_store import CompoundVectorStore
from application.ports.permission_registrar import PermissionRegistrar
from application.ports.summary_vector_store import SummaryVectorStore
from application.ports.vector_store import VectorStore

if TYPE_CHECKING:
    from application.ports.auth import AuthContext

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

    async def execute(
        self, request: CreateArtifactRequest, auth: AuthContext | None = None
    ) -> Result[ArtifactResponse, AppError]:
        try:
            if auth and not auth.has_role("editor"):
                return Failure(AppError("forbidden", "Requires editor role"))

            # Create a new Artifact aggregate
            artifact = Artifact.create(
                source_uri=request.source_uri,
                source_filename=request.source_filename,
                artifact_type=request.artifact_type,
                mime_type=request.mime_type,
                storage_location=request.storage_location,
                workspace_id=auth.workspace_id if auth else None,
                owner_id=auth.user_id if auth else None,
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
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        try:
            if auth and not auth.has_role("editor"):
                return Failure(AppError("forbidden", "Requires editor role"))

            # Retrieve the artifact by ID
            artifact = self.artifact_repository.get_by_id(artifact_id)

            if auth and artifact.workspace_id is not None and artifact.workspace_id != auth.workspace_id:
                return Failure(AppError("not_found", "Artifact not found"))

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
                await self.external_event_publisher.notify_artifact_updated(
                    result, sub_type="PagesAdded"
                )

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
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        try:
            if auth and not auth.has_role("editor"):
                return Failure(AppError("forbidden", "Requires editor role"))

            # Retrieve the artifact by ID
            artifact = self.artifact_repository.get_by_id(artifact_id)

            if auth and artifact.workspace_id is not None and artifact.workspace_id != auth.workspace_id:
                return Failure(AppError("not_found", "Artifact not found"))

            # Remove pages from the artifact
            artifact.remove_pages(page_ids)

            # Save the updated artifact
            self.artifact_repository.save(artifact)

            # Return a successful result with the updated ArtifactResponse
            result = ArtifactMapper.to_artifact_response(artifact)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_artifact_updated(
                    result, sub_type="PagesRemoved"
                )

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
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        try:
            if auth and not auth.has_role("editor"):
                return Failure(AppError("forbidden", "Requires editor role"))

            logger.info(
                "update_title_mention_use_case_start",
                artifact_id=str(artifact_id),
                title_mention=title_mention,
                title_mention_type=type(title_mention).__name__ if title_mention else "None",
            )
            # Retrieve the artifact by ID
            logger.info("retrieving_artifact", artifact_id=str(artifact_id))
            artifact = self.artifact_repository.get_by_id(artifact_id)

            if auth and artifact.workspace_id is not None and artifact.workspace_id != auth.workspace_id:
                return Failure(AppError("not_found", "Artifact not found"))

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
                await self.external_event_publisher.notify_artifact_updated(
                    result, sub_type="TitleMentionUpdated"
                )
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
            logger.exception(
                "unexpected_error_in_update_title_mention_use_case",
                artifact_id=str(artifact_id),
                error=str(e),
                error_type=type(e).__name__,
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
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        try:
            if auth and not auth.has_role("editor"):
                return Failure(AppError("forbidden", "Requires editor role"))

            # Retrieve the artifact by ID
            artifact = self.artifact_repository.get_by_id(artifact_id)

            if auth and artifact.workspace_id is not None and artifact.workspace_id != auth.workspace_id:
                return Failure(AppError("not_found", "Artifact not found"))

            # Update summary candidate
            artifact.update_summary_candidate(summary_candidate)

            # Save the updated artifact
            self.artifact_repository.save(artifact)

            # Return a successful result with the updated ArtifactResponse
            result = ArtifactMapper.to_artifact_response(artifact)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_artifact_updated(
                    result, sub_type="SummaryCandidateUpdated"
                )

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
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        try:
            if auth and not auth.has_role("editor"):
                return Failure(AppError("forbidden", "Requires editor role"))

            # Retrieve the artifact by ID
            artifact = self.artifact_repository.get_by_id(artifact_id)

            if auth and artifact.workspace_id is not None and artifact.workspace_id != auth.workspace_id:
                return Failure(AppError("not_found", "Artifact not found"))

            # Update tags
            artifact.update_tags(tags)

            # Save the updated artifact
            self.artifact_repository.save(artifact)

            # Return a successful result with the updated ArtifactResponse
            result = ArtifactMapper.to_artifact_response(artifact)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_artifact_updated(
                    result, sub_type="TagsUpdated"
                )

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
    """Delete an artifact and all its associated pages.

    After the event-sourced deletion, performs best-effort cleanup of
    secondary stores (vector DBs, blob storage).  Cleanup failures are
    logged but never fail the overall operation.
    """

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
        vector_store: VectorStore | None = None,
        compound_vector_store: CompoundVectorStore | None = None,
        summary_vector_store: SummaryVectorStore | None = None,
        blob_store: BlobStore | None = None,
        permission_registrar: PermissionRegistrar | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher
        self._vector_store = vector_store
        self._compound_vector_store = compound_vector_store
        self._summary_vector_store = summary_vector_store
        self._blob_store = blob_store
        self._permission_registrar = permission_registrar

    async def execute(
        self, artifact_id: UUID, auth: AuthContext | None = None
    ) -> Result[None, AppError]:
        try:
            if auth and not auth.has_role("editor"):
                return Failure(AppError("forbidden", "Requires editor role"))

            # Retrieve the artifact and its pages
            artifact = self.artifact_repository.get_by_id(artifact_id)

            if auth and artifact.workspace_id is not None and artifact.workspace_id != auth.workspace_id:
                return Failure(AppError("not_found", "Artifact not found"))

            page_ids = list(artifact.pages)
            storage_location = artifact.storage_location
            pages = [self.page_repository.get_by_id(pid) for pid in page_ids]

            # Use the domain service to delete artifact and all its pages
            ArtifactDeletionService.delete_artifact_with_pages(artifact, pages)

            # Persist all deleted aggregates
            for page in pages:
                self.page_repository.save(page)
            self.artifact_repository.save(artifact)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_artifact_deleted(artifact_id)

            # Best-effort cleanup of secondary stores
            await self._cleanup_secondary_stores(artifact_id, page_ids, storage_location)

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

    async def _cleanup_secondary_stores(
        self,
        artifact_id: UUID,
        page_ids: list[UUID],
        storage_location: str,
    ) -> None:
        """Best-effort cleanup — errors are logged, never raised."""
        for page_id in page_ids:
            if self._vector_store:
                try:
                    await self._vector_store.delete_page_embedding(page_id)
                except Exception:
                    logger.warning("cleanup_page_embedding_failed", page_id=str(page_id), exc_info=True)

            if self._compound_vector_store:
                try:
                    await self._compound_vector_store.delete_compound_embeddings_for_page(page_id)
                except Exception:
                    logger.warning("cleanup_compound_embedding_failed", page_id=str(page_id), exc_info=True)

            if self._summary_vector_store:
                try:
                    await self._summary_vector_store.delete_page_summary(page_id)
                except Exception:
                    logger.warning("cleanup_page_summary_embedding_failed", page_id=str(page_id), exc_info=True)

        if self._summary_vector_store:
            try:
                await self._summary_vector_store.delete_artifact_summary(artifact_id)
            except Exception:
                logger.warning("cleanup_artifact_summary_embedding_failed", artifact_id=str(artifact_id), exc_info=True)

        if self._blob_store and storage_location:
            try:
                self._blob_store.delete(storage_location)
            except Exception:
                logger.warning("cleanup_blob_failed", storage_location=storage_location, exc_info=True)

        if self._permission_registrar:
            try:
                await self._permission_registrar.deregister_resource("artifact", artifact_id)
            except Exception:
                logger.warning("cleanup_permission_failed", artifact_id=str(artifact_id), exc_info=True)

        logger.info(
            "secondary_store_cleanup_complete",
            artifact_id=str(artifact_id),
            pages_cleaned=len(page_ids),
        )
