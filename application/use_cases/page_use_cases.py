from uuid import UUID

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.dtos.page_dtos import AddCompoundMentionsRequest, CreatePageRequest, PageResponse
from application.mappers.page_mappers import PageMapper
from application.ports.external_event_publisher import ExternalEventPublisher
from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.repositories.page_repository import PageRepository
from domain.aggregates.page import Page
from domain.exceptions import (
    AggregateNotFoundError,
    ConcurrencyError,
    ValidationError,
)
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

    async def execute(self, request: CreatePageRequest) -> Result[PageResponse, AppError]:
        try:
            logger.info(
                "create_page_use_case_start",
                artifact_id=str(request.artifact_id),
                page_name=request.name,
            )
            # Create a new Page aggregate
            page = Page.create(
                name=request.name,
                artifact_id=request.artifact_id,
                index=request.index,
            )

            # Save the Page using the repository
            logger.info("saving_page", page_id=str(page.id))
            self.page_repository.save(page)
            logger.info("page_saved", page_id=str(page.id))

            # Update the artifact to reference this page
            logger.info(
                "updating_artifact_with_page",
                artifact_id=str(request.artifact_id),
                page_id=str(page.id),
            )
            artifact = self.artifact_repository.get_by_id(request.artifact_id)
            artifact.add_pages([page.id])
            self.artifact_repository.save(artifact)
            logger.info("artifact_updated_with_page", artifact_id=str(request.artifact_id))

            result = PageMapper.to_page_response(page)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_page_created(result)

            logger.info("create_page_use_case_success", page_id=str(page.id))
            # Return a successful result with the PageResponse
            return Success(result)
        except AggregateNotFoundError as e:
            logger.warning("artifact_not_found", artifact_id=str(request.artifact_id), error=str(e))
            return Failure(AppError("not_found", f"Artifact not found: {e!s}"))
        except ValidationError as e:
            logger.warning("validation_error", error=str(e))
            # Domain validation errors - client's fault (400 Bad Request)
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            logger.warning("concurrency_error", error=str(e))
            # Concurrency conflicts (409 Conflict)
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except Exception as e:
            logger.error(
                "unexpected_error_in_create_page_use_case",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))


class AddCompoundMentionsUseCase:
    def __init__(
        self,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    async def execute(self, request: AddCompoundMentionsRequest) -> Result[PageResponse, AppError]:
        try:
            # Retrieve the page by ID
            page = self.page_repository.get_by_id(request.page_id)

            # Add compound_mentions to the page
            page.update_compound_mentions(request.compound_mentions)

            # Save the updated page
            self.page_repository.save(page)

            # Return a successful result with the updated PageResponse
            result = PageMapper.to_page_response(page)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_page_updated(result)

            return Success(result)
        except AggregateNotFoundError as e:
            # Page not found - client's fault (404 Not Found)
            return Failure(AppError("not_found", f"Page not found: {e!s}"))
        except ValidationError as e:
            # Domain validation errors - client's fault (400 Bad Request)
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            # Concurrency conflicts (409 Conflict) - retry-able error
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )


class UpdateTagMentionsUseCase:
    """Update tag mentions for a page."""

    def __init__(
        self,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    async def execute(
        self,
        page_id: UUID,
        tag_mentions: list[TagMention],
    ) -> Result[PageResponse, AppError]:
        try:
            # Retrieve the page by ID
            page = self.page_repository.get_by_id(page_id)

            # Update tag mentions
            page.update_tag_mentions(tag_mentions)

            # Save the updated page
            self.page_repository.save(page)

            # Return a successful result with the updated PageResponse
            result = PageMapper.to_page_response(page)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_page_updated(result)

            return Success(result)
        except AggregateNotFoundError as e:
            return Failure(AppError("not_found", f"Page not found: {e!s}"))
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except ValueError as e:
            return Failure(AppError("invalid_operation", str(e)))


class UpdateTextMentionUseCase:
    """Update text mention for a page."""

    def __init__(
        self,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    async def execute(
        self,
        page_id: UUID,
        text_mention: TextMention,
    ) -> Result[PageResponse, AppError]:
        try:
            # Retrieve the page by ID
            page = self.page_repository.get_by_id(page_id)

            # Update text mention
            page.update_text_mention(text_mention)

            # Save the updated page
            self.page_repository.save(page)

            # Return a successful result with the updated PageResponse
            result = PageMapper.to_page_response(page)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_page_updated(result)

            return Success(result)
        except AggregateNotFoundError as e:
            return Failure(AppError("not_found", f"Page not found: {e!s}"))
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except ValueError as e:
            return Failure(AppError("invalid_operation", str(e)))


class UpdateSummaryCandidateUseCase:
    """Update summary candidate for a page."""

    def __init__(
        self,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    async def execute(
        self,
        page_id: UUID,
        summary_candidate: SummaryCandidate,
    ) -> Result[PageResponse, AppError]:
        try:
            # Retrieve the page by ID
            page = self.page_repository.get_by_id(page_id)

            # Update summary candidate
            page.update_summary_candidate(summary_candidate)

            # Save the updated page
            self.page_repository.save(page)

            # Return a successful result with the updated PageResponse
            result = PageMapper.to_page_response(page)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_page_updated(result)

            return Success(result)
        except AggregateNotFoundError as e:
            return Failure(AppError("not_found", f"Page not found: {e!s}"))
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except ValueError as e:
            return Failure(AppError("invalid_operation", str(e)))


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

    async def execute(self, page_id: UUID) -> Result[None, AppError]:
        try:
            logger.info("delete_page_use_case_start", page_id=str(page_id))
            # Retrieve the page by ID
            page = self.page_repository.get_by_id(page_id)

            # Delete the page
            logger.info("deleting_page", page_id=str(page_id))
            page.delete()

            # Save the updated page
            logger.info("saving_deleted_page", page_id=str(page_id))
            self.page_repository.save(page)
            logger.info("deleted_page_saved", page_id=str(page_id))

            # Remove page from artifact
            logger.info(
                "removing_page_from_artifact",
                page_id=str(page_id),
                artifact_id=str(page.artifact_id),
            )
            artifact = self.artifact_repository.get_by_id(page.artifact_id)
            artifact.remove_pages([page_id])
            self.artifact_repository.save(artifact)
            logger.info("artifact_updated_page_removed", artifact_id=str(page.artifact_id))

            if self.external_event_publisher:
                await self.external_event_publisher.notify_page_deleted(page_id)

            logger.info("delete_page_use_case_success", page_id=str(page_id))
            # Return a successful result
            return Success(None)
        except AggregateNotFoundError as e:
            logger.warning("aggregate_not_found", page_id=str(page_id), error=str(e))
            return Failure(AppError("not_found", f"Page not found: {e!s}"))
        except ValidationError as e:
            logger.warning("validation_error", page_id=str(page_id), error=str(e))
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            logger.warning("concurrency_error", page_id=str(page_id), error=str(e))
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except ValueError as e:
            logger.warning("value_error", page_id=str(page_id), error=str(e))
            return Failure(AppError("invalid_operation", str(e)))
        except Exception as e:
            logger.error(
                "unexpected_error_in_delete_page_use_case",
                page_id=str(page_id),
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))
