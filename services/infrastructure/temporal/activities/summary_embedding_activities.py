"""Temporal activities for embedding page and artifact summaries."""

from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.summary_embedding_use_cases import (
    EmbedArtifactSummaryUseCase,
    EmbedPageSummaryUseCase,
)

logger = structlog.get_logger()


def create_embed_page_summary_activity(
    use_case: EmbedPageSummaryUseCase,
) -> Callable[[str], dict]:
    """Return the embed_page_summary Temporal activity."""

    @activity.defn(name="embed_page_summary")
    async def embed_page_summary_activity(page_id: str) -> dict:
        logger.info("embed_page_summary_activity.start", page_id=page_id)

        try:
            page_uuid = UUID(page_id)
            result = await use_case.execute(page_id=page_uuid)
        except Exception as e:
            logger.exception(
                "embed_page_summary_activity.exception",
                page_id=page_id,
                error=str(e),
            )
            raise
        else:
            if isinstance(result, Success):
                logger.info("embed_page_summary_activity.success", page_id=page_id)
                return result.unwrap()

            error = result.failure()
            logger.error(
                "embed_page_summary_activity.failed",
                page_id=page_id,
                error_code=error.category,
                error_message=error.message,
            )
            if error.category == "concurrency":
                msg = f"Concurrency conflict (will retry): {error.message}"
                raise RuntimeError(msg)
            # validation / not_found are non-retryable — return status dict
            return {
                "status": "failed",
                "page_id": page_id,
                "error_code": error.category,
                "error_message": error.message,
            }

    return embed_page_summary_activity


def create_embed_artifact_summary_activity(
    use_case: EmbedArtifactSummaryUseCase,
) -> Callable[[str], dict]:
    """Return the embed_artifact_summary Temporal activity."""

    @activity.defn(name="embed_artifact_summary")
    async def embed_artifact_summary_activity(artifact_id: str) -> dict:
        logger.info("embed_artifact_summary_activity.start", artifact_id=artifact_id)

        try:
            artifact_uuid = UUID(artifact_id)
            result = await use_case.execute(artifact_id=artifact_uuid)
        except Exception as e:
            logger.exception(
                "embed_artifact_summary_activity.exception",
                artifact_id=artifact_id,
                error=str(e),
            )
            raise
        else:
            if isinstance(result, Success):
                logger.info("embed_artifact_summary_activity.success", artifact_id=artifact_id)
                return result.unwrap()

            error = result.failure()
            logger.error(
                "embed_artifact_summary_activity.failed",
                artifact_id=artifact_id,
                error_code=error.category,
                error_message=error.message,
            )
            if error.category == "concurrency":
                msg = f"Concurrency conflict (will retry): {error.message}"
                raise RuntimeError(msg)
            return {
                "status": "failed",
                "artifact_id": artifact_id,
                "error_code": error.category,
                "error_message": error.message,
            }

    return embed_artifact_summary_activity
