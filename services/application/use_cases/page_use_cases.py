from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Result, Success

from application.mappers.page_mappers import PageMapper
from application.use_cases._guards import (
    handle_domain_errors,
    require_editor,
    require_page_workspace,
)
from domain.aggregates.page import Page

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.errors import AppError
    from application.dtos.page_dtos import (
        AddCompoundMentionsRequest,
        CreatePageRequest,
        PageResponse,
    )
    from application.ports.auth import AuthContext
    from application.ports.external_event_publisher import ExternalEventPublisher
    from application.ports.repositories.artifact_repository import ArtifactRepository
    from application.ports.repositories.page_repository import PageRepository
    from domain.value_objects.summary_candidate import SummaryCandidate
    from domain.value_objects.tag_mention import TagMention
    from domain.value_objects.text_mention import TextMention

logger = structlog.get_logger()


class CreatePageUseCase:
    def __init__(
        self,
        page_repository: PageRepository,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        request: CreatePageRequest,
        auth: AuthContext | None = None,
    ) -> Result[PageResponse, AppError]:
        require_editor(auth)

        logger.info(
            "create_page_use_case_start",
            artifact_id=str(request.artifact_id),
            page_name=request.name,
        )
        # Ensure artifact exists before creating a page
        self.artifact_repository.get_by_id(request.artifact_id)

        page = Page.create(
            name=request.name,
            artifact_id=request.artifact_id,
            index=request.index,
            workspace_id=auth.workspace_id if auth else None,
            owner_id=auth.user_id if auth else None,
        )

        self.page_repository.save(page)

        result = PageMapper.to_page_response(page)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_page_created(result)

        logger.info("create_page_use_case_success", page_id=str(page.id))
        return Success(result)


class AddCompoundMentionsUseCase:
    def __init__(
        self,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        request: AddCompoundMentionsRequest,
        auth: AuthContext | None = None,
    ) -> Result[PageResponse, AppError]:
        require_editor(auth)

        page = self.page_repository.get_by_id(request.page_id)
        require_page_workspace(auth, page)

        page.update_compound_mentions(request.compound_mentions)
        self.page_repository.save(page)

        result = PageMapper.to_page_response(page)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_page_updated(
                result,
                sub_type="CompoundMentionsUpdated",
            )

        return Success(result)


class UpdateTagMentionsUseCase:
    """Update tag mentions for a page."""

    def __init__(
        self,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        page_id: UUID,
        tag_mentions: list[TagMention],
        auth: AuthContext | None = None,
    ) -> Result[PageResponse, AppError]:
        require_editor(auth)

        page = self.page_repository.get_by_id(page_id)
        require_page_workspace(auth, page)

        page.update_tag_mentions(tag_mentions)
        self.page_repository.save(page)

        result = PageMapper.to_page_response(page)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_page_updated(
                result,
                sub_type="TagMentionsUpdated",
            )

        return Success(result)


class UpdateTextMentionUseCase:
    """Update text mention for a page."""

    def __init__(
        self,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        page_id: UUID,
        text_mention: TextMention,
        auth: AuthContext | None = None,
    ) -> Result[PageResponse, AppError]:
        require_editor(auth)

        page = self.page_repository.get_by_id(page_id)
        require_page_workspace(auth, page)

        page.update_text_mention(text_mention)
        self.page_repository.save(page)

        result = PageMapper.to_page_response(page)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_page_updated(
                result,
                sub_type="TextMentionUpdated",
            )

        return Success(result)


class UpdateSummaryCandidateUseCase:
    """Update summary candidate for a page."""

    def __init__(
        self,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        page_id: UUID,
        summary_candidate: SummaryCandidate,
        auth: AuthContext | None = None,
    ) -> Result[PageResponse, AppError]:
        require_editor(auth)

        page = self.page_repository.get_by_id(page_id)
        require_page_workspace(auth, page)

        page.update_summary_candidate(summary_candidate)
        self.page_repository.save(page)

        result = PageMapper.to_page_response(page)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_page_updated(
                result,
                sub_type="SummaryCandidateUpdated",
            )

        return Success(result)


class DeletePageUseCase:
    """Delete a page."""

    def __init__(
        self,
        page_repository: PageRepository,
        artifact_repository: ArtifactRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.artifact_repository = artifact_repository
        self.external_event_publisher = external_event_publisher

    @handle_domain_errors
    async def execute(
        self,
        page_id: UUID,
        auth: AuthContext | None = None,
    ) -> Result[None, AppError]:
        require_editor(auth)

        logger.info("delete_page_use_case_start", page_id=str(page_id))

        page = self.page_repository.get_by_id(page_id)
        require_page_workspace(auth, page)

        page.delete()
        self.page_repository.save(page)

        # Remove page from artifact
        artifact = self.artifact_repository.get_by_id(page.artifact_id)
        artifact.remove_pages([page_id])
        self.artifact_repository.save(artifact)

        if self.external_event_publisher:
            await self.external_event_publisher.notify_page_deleted(page_id)

        logger.info("delete_page_use_case_success", page_id=str(page_id))
        return Success(None)
