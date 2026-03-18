"""Use case: run NER on a page's text and store typed TagMentions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from domain.value_objects.tag_mention import TagMention

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.external_event_publisher import ExternalEventPublisher
    from application.ports.ner_extractor import NERExtractorPort
    from application.ports.repositories.artifact_repository import ArtifactRepository
    from application.ports.repositories.page_repository import PageRepository

logger = structlog.get_logger()


class ExtractPageEntitiesUseCase:
    """Run fast + LLM NER on page text, store results as TagMentions.

    Reads page.text_mention.text, calls the NER extractor (which runs both
    fast and LLM modes internally), maps the output to TagMention value objects,
    and persists them via page.update_tag_mentions().
    """

    def __init__(
        self,
        page_repository: PageRepository,
        artifact_repository: ArtifactRepository,
        ner_extractor: NERExtractorPort,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.artifact_repository = artifact_repository
        self.ner_extractor = ner_extractor
        self.external_event_publisher = external_event_publisher

    async def execute(self, page_id: UUID) -> Result[dict, AppError]:
        try:
            page = self.page_repository.get_by_id(page_id)

            if page.text_mention is None or not page.text_mention.text:
                logger.info(
                    "extract_page_entities.skip_no_text",
                    page_id=str(page_id),
                )
                return Success({"status": "skipped", "reason": "no text", "page_id": str(page_id)})

            artifact = self.artifact_repository.get_by_id(page.artifact_id)
            model_label = f"structflo-ner/{artifact.source_filename or 'unknown'}"

            logger.info(
                "extract_page_entities.start",
                page_id=str(page_id),
                text_len=len(page.text_mention.text),
            )

            raw_entities = await self.ner_extractor.extract(page.text_mention.text)

            tag_mentions = [
                TagMention(
                    tag=entity.text,
                    entity_type=entity.entity_type,
                    confidence=entity.confidence,
                    date_extracted=datetime.now(UTC),
                    model_name="structflo-ner",
                    additional_model_params={"entity_type": entity.entity_type}
                    | (entity.attributes or {}),
                    pipeline_run_id=None,
                )
                for entity in raw_entities
                if entity.text and entity.text.strip()
            ]

            page.update_tag_mentions(tag_mentions)
            self.page_repository.save(page)

            if self.external_event_publisher:
                from application.mappers.page_mappers import PageMapper  # noqa: PLC0415

                page_response = PageMapper.to_page_response(page)
                await self.external_event_publisher.notify_page_updated(
                    page_response,
                    sub_type="TagMentionsUpdated",
                )

            logger.info(
                "extract_page_entities.success",
                page_id=str(page_id),
                entity_count=len(tag_mentions),
            )
            _ = model_label  # used for future tracing; suppress unused warning

            return Success(
                {
                    "status": "success",
                    "page_id": str(page_id),
                    "entity_count": len(tag_mentions),
                },
            )

        except Exception as e:
            from eventsourcing.application import AggregateNotFoundError  # noqa: PLC0415

            from infrastructure.event_sourced_repositories.page_repository import (  # noqa: PLC0415
                ConcurrencyError,
            )

            if isinstance(e, AggregateNotFoundError):
                return Failure(AppError("not_found", str(e)))
            if isinstance(e, ConcurrencyError):
                return Failure(AppError("concurrency", str(e)))
            logger.exception("extract_page_entities.error", page_id=str(page_id))
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))
