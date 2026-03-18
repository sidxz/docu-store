from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.mappers.artifact_mappers import ArtifactMapper
from application.use_cases._guards import (
    handle_domain_errors,
    require_artifact_workspace,
    require_editor,
)
from domain.aggregates.artifact import Artifact
from domain.services.artifact_deletion_service import ArtifactDeletionService

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.artifact_dtos import ArtifactResponse, CreateArtifactRequest
    from application.ports.auth import AuthContext
    from application.ports.blob_store import BlobStore
    from application.ports.compound_vector_store import CompoundVectorStore
    from application.ports.external_event_publisher import ExternalEventPublisher
    from application.ports.permission_registrar import PermissionRegistrar
    from application.ports.repositories.artifact_repository import ArtifactRepository
    from application.ports.repositories.page_repository import PageRepository
    from application.ports.summary_vector_store import SummaryVectorStore
    from application.ports.vector_store import VectorStore
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

    @handle_domain_errors
    async def execute(
        self,
        request: CreateArtifactRequest,
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        require_editor(auth)

        artifact = Artifact.create(
            source_uri=request.source_uri,
            source_filename=request.source_filename,
            artifact_type=request.artifact_type,
            mime_type=request.mime_type,
            storage_location=request.storage_location,
            workspace_id=auth.workspace_id if auth else None,
            owner_id=auth.user_id if auth else None,
        )

        self.artifact_repository.save(artifact)

        result = ArtifactMapper.to_artifact_response(artifact)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_artifact_created(result)

        return Success(result)


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

    @handle_domain_errors
    async def execute(
        self,
        artifact_id: UUID,
        page_ids: list[UUID],
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        require_editor(auth)

        artifact = self.artifact_repository.get_by_id(artifact_id)
        require_artifact_workspace(auth, artifact)

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

        artifact.add_pages(page_ids)
        self.artifact_repository.save(artifact)

        result = ArtifactMapper.to_artifact_response(artifact)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_artifact_updated(
                result,
                sub_type="PagesAdded",
            )

        return Success(result)


class RemovePagesUseCase:
    """Remove pages from an artifact."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        artifact_id: UUID,
        page_ids: list[UUID],
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        require_editor(auth)

        artifact = self.artifact_repository.get_by_id(artifact_id)
        require_artifact_workspace(auth, artifact)

        artifact.remove_pages(page_ids)
        self.artifact_repository.save(artifact)

        result = ArtifactMapper.to_artifact_response(artifact)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_artifact_updated(
                result,
                sub_type="PagesRemoved",
            )

        return Success(result)


class UpdateTitleMentionUseCase:
    """Update title mention for an artifact."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        artifact_id: UUID,
        title_mention: TitleMention | None,
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        require_editor(auth)

        logger.info(
            "update_title_mention_use_case_start",
            artifact_id=str(artifact_id),
            title_mention=title_mention,
            title_mention_type=type(title_mention).__name__ if title_mention else "None",
        )

        artifact = self.artifact_repository.get_by_id(artifact_id)
        require_artifact_workspace(auth, artifact)

        artifact.update_title_mention(title_mention)
        self.artifact_repository.save(artifact)

        result = ArtifactMapper.to_artifact_response(artifact)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_artifact_updated(
                result,
                sub_type="TitleMentionUpdated",
            )

        logger.info("update_title_mention_use_case_success", artifact_id=str(artifact_id))
        return Success(result)


class UpdateSummaryCandidateUseCase:
    """Update summary candidate for an artifact."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        artifact_id: UUID,
        summary_candidate: SummaryCandidate | None,
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        require_editor(auth)

        artifact = self.artifact_repository.get_by_id(artifact_id)
        require_artifact_workspace(auth, artifact)

        artifact.update_summary_candidate(summary_candidate)
        self.artifact_repository.save(artifact)

        result = ArtifactMapper.to_artifact_response(artifact)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_artifact_updated(
                result,
                sub_type="SummaryCandidateUpdated",
            )

        return Success(result)


class UpdateTagsUseCase:
    """Update tags for an artifact."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        artifact_id: UUID,
        tags: list[str],
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        require_editor(auth)

        artifact = self.artifact_repository.get_by_id(artifact_id)
        require_artifact_workspace(auth, artifact)

        artifact.update_tags(tags)
        self.artifact_repository.save(artifact)

        result = ArtifactMapper.to_artifact_response(artifact)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_artifact_updated(
                result,
                sub_type="TagsUpdated",
            )

        return Success(result)


class DeleteArtifactUseCase:
    """Delete an artifact and all its associated pages.

    After the event-sourced deletion, performs best-effort cleanup of
    secondary stores (vector DBs, blob storage).  Cleanup failures are
    logged but never fail the overall operation.
    """

    def __init__(  # noqa: PLR0913
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

    @handle_domain_errors
    async def execute(
        self,
        artifact_id: UUID,
        auth: AuthContext | None = None,
    ) -> Result[None, AppError]:
        require_editor(auth)

        artifact = self.artifact_repository.get_by_id(artifact_id)
        require_artifact_workspace(auth, artifact)

        page_ids = list(artifact.pages)
        storage_location = artifact.storage_location
        pages = [self.page_repository.get_by_id(pid) for pid in page_ids]

        ArtifactDeletionService.delete_artifact_with_pages(artifact, pages)

        for page in pages:
            self.page_repository.save(page)
        self.artifact_repository.save(artifact)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_artifact_deleted(artifact_id)

        await self._cleanup_secondary_stores(artifact_id, page_ids, storage_location)

        return Success(None)

    async def _cleanup_secondary_stores(
        self,
        artifact_id: UUID,
        page_ids: list[UUID],
        storage_location: str,
    ) -> None:
        """Best-effort cleanup — errors are logged, never raised."""
        for page_id in page_ids:
            await self._cleanup_page_stores(page_id)
        await self._cleanup_artifact_stores(artifact_id, storage_location)

        logger.info(
            "secondary_store_cleanup_complete",
            artifact_id=str(artifact_id),
            pages_cleaned=len(page_ids),
        )

    async def _cleanup_page_stores(self, page_id: UUID) -> None:
        """Best-effort cleanup of all vector stores for a single page."""
        await _safe_cleanup(
            self._vector_store,
            "delete_page_embedding",
            "page_embedding",
            page_id=str(page_id),
            args=(page_id,),
        )
        await _safe_cleanup(
            self._compound_vector_store,
            "delete_compound_embeddings_for_page",
            "compound_embedding",
            page_id=str(page_id),
            args=(page_id,),
        )
        await _safe_cleanup(
            self._summary_vector_store,
            "delete_page_summary",
            "page_summary_embedding",
            page_id=str(page_id),
            args=(page_id,),
        )

    async def _cleanup_artifact_stores(
        self,
        artifact_id: UUID,
        storage_location: str,
    ) -> None:
        """Best-effort cleanup of artifact-level stores."""
        await _safe_cleanup(
            self._summary_vector_store,
            "delete_artifact_summary",
            "artifact_summary_embedding",
            artifact_id=str(artifact_id),
            args=(artifact_id,),
        )
        if self._blob_store and storage_location:
            await _safe_cleanup(
                self._blob_store,
                "delete",
                "blob",
                storage_location=storage_location,
                args=(storage_location,),
                is_sync=True,
            )
        await _safe_cleanup(
            self._permission_registrar,
            "deregister_resource",
            "permission",
            artifact_id=str(artifact_id),
            args=("artifact", artifact_id),
        )


async def _safe_cleanup(
    store: object | None,
    method_name: str,
    label: str,
    *,
    args: tuple = (),
    is_sync: bool = False,
    **log_kwargs: str,
) -> None:
    """Call *store.method_name(*args)* and swallow any exception."""
    if store is None:
        return
    try:
        result = getattr(store, method_name)(*args)
        if not is_sync:
            await result
    except Exception:  # noqa: BLE001
        logger.warning("cleanup_%s_failed", label, exc_info=True, **log_kwargs)
