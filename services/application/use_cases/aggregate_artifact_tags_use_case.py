"""Use case: aggregate NER tags from all pages into artifact-level tags."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.external_event_publisher import ExternalEventPublisher
    from application.ports.repositories.artifact_repository import ArtifactRepository
    from application.ports.repositories.page_repository import PageRepository

logger = structlog.get_logger()


class AggregateArtifactTagsUseCase:
    """Collect all TagMention.tag strings from every page of an artifact.

    Refreshes Artifact.tags with the deduplicated union.

    This use case is idempotent and re-entrant: re-running it after any page
    receives new tag_mentions simply refreshes the artifact's tag list.
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

            all_tags: list[str] = []
            pages_loaded = 0
            for page_id in artifact.pages:
                try:
                    page = self.page_repository.get_by_id(page_id)
                    all_tags.extend(m.tag for m in page.tag_mentions if m.tag)
                    pages_loaded += 1
                except Exception:  # noqa: BLE001
                    # Skip pages that can't be loaded — partial aggregation is fine
                    logger.warning(
                        "aggregate_artifact_tags.page_load_failed",
                        artifact_id=str(artifact_id),
                        page_id=str(page_id),
                    )

            # Preserve first-seen order, deduplicate case-insensitively but keep
            # the original casing of the first occurrence.
            seen_lower: set[str] = set()
            deduped: list[str] = []
            for tag in all_tags:
                key = tag.strip().lower()
                if key and key not in seen_lower:
                    deduped.append(tag.strip())
                    seen_lower.add(key)

            artifact.update_tags(deduped)
            self.artifact_repository.save(artifact)

            if self.external_event_publisher:
                from application.mappers.artifact_mappers import ArtifactMapper  # noqa: PLC0415

                artifact_response = ArtifactMapper.to_artifact_response(artifact)
                await self.external_event_publisher.notify_artifact_updated(
                    artifact_response,
                    sub_type="TagsUpdated",
                )

            logger.info(
                "aggregate_artifact_tags.success",
                artifact_id=str(artifact_id),
                pages_loaded=pages_loaded,
                tag_count=len(deduped),
            )
            return Success(
                {
                    "status": "success",
                    "artifact_id": str(artifact_id),
                    "pages_loaded": pages_loaded,
                    "tag_count": len(deduped),
                },
            )

        except Exception as e:
            from eventsourcing.application import AggregateNotFoundError  # noqa: PLC0415

            from infrastructure.event_sourced_repositories.artifact_repository import (  # noqa: PLC0415
                ConcurrencyError,
            )

            if isinstance(e, AggregateNotFoundError):
                return Failure(AppError("not_found", str(e)))
            if isinstance(e, ConcurrencyError):
                return Failure(AppError("concurrency", str(e)))
            logger.exception("aggregate_artifact_tags.error", artifact_id=str(artifact_id))
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))
