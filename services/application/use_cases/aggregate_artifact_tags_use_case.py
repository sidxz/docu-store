"""Use case: aggregate NER tag mentions from all pages into artifact-level tag mentions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from domain.services.tag_mention_aggregator import aggregate_tag_mentions

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.external_event_publisher import ExternalEventPublisher
    from application.ports.repositories.artifact_repository import ArtifactRepository
    from application.ports.repositories.page_repository import PageRepository

logger = structlog.get_logger()


class AggregateArtifactTagsUseCase:
    """Collect TagMentions from every page of an artifact and merge them.

    Uses the ``aggregate_tag_mentions`` domain service to deduplicate across
    pages and merge compound bioactivities.  The result is stored on the
    artifact via ``update_tag_mentions()``.

    This use case is idempotent and re-entrant: re-running it after any page
    receives new tag_mentions simply refreshes the artifact's tag mention list.
    """

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    async def execute(self, artifact_id: UUID) -> Result[dict, AppError]:
        try:
            artifact = self.artifact_repository.get_by_id(artifact_id)

            pages_data = []
            pages_loaded = 0
            for page_id in artifact.pages:
                try:
                    page = self.page_repository.get_by_id(page_id)
                    pages_data.append((page.id, page.index, list(page.tag_mentions)))
                    pages_loaded += 1
                except Exception:  # noqa: BLE001
                    # Skip pages that can't be loaded — partial aggregation is fine
                    logger.warning(
                        "aggregate_artifact_tags.page_load_failed",
                        artifact_id=str(artifact_id),
                        page_id=str(page_id),
                    )

            merged = aggregate_tag_mentions(pages_data)

            artifact.update_tag_mentions(merged)
            self.artifact_repository.save(artifact)

            if self.external_event_publisher:
                from application.mappers.artifact_mappers import ArtifactMapper  # noqa: PLC0415

                artifact_response = ArtifactMapper.to_artifact_response(artifact)
                await self.external_event_publisher.notify_artifact_updated(
                    artifact_response,
                    sub_type="TagMentionsUpdated",
                )

            logger.info(
                "aggregate_artifact_tags.success",
                artifact_id=str(artifact_id),
                pages_loaded=pages_loaded,
                tag_count=len(merged),
            )
            return Success(
                {
                    "status": "success",
                    "artifact_id": str(artifact_id),
                    "pages_loaded": pages_loaded,
                    "tag_count": len(merged),
                },
            )

        except Exception as e:
            from domain.exceptions import AggregateNotFoundError, ConcurrencyError  # noqa: PLC0415

            if isinstance(e, AggregateNotFoundError):
                return Failure(AppError("not_found", str(e)))
            if isinstance(e, ConcurrencyError):
                return Failure(AppError("concurrency", str(e)))
            logger.exception("aggregate_artifact_tags.error", artifact_id=str(artifact_id))
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))
