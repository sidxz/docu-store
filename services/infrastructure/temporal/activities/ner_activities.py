from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.aggregate_artifact_tags_use_case import AggregateArtifactTagsUseCase
from application.use_cases.extract_page_entities_use_case import ExtractPageEntitiesUseCase
from domain.exceptions import LLMError
from infrastructure.temporal.activities.errors import (
    failure_to_application_error,
    llm_error_to_application_error,
)

logger = structlog.get_logger()


def create_extract_page_entities_activity(
    use_case: ExtractPageEntitiesUseCase,
) -> Callable[[str], dict]:
    """Create the extract_page_entities activity with injected dependencies."""

    @activity.defn(name="extract_page_entities")
    async def extract_page_entities_activity(page_id: str) -> dict:
        logger.info("extract_page_entities_activity.start", page_id=page_id)

        try:
            result = await use_case.execute(page_id=UUID(page_id))
        except LLMError as e:
            logger.error(  # noqa: TRY400 -- expected/typed failure, no traceback needed
                "extract_page_entities_activity.llm_error",
                page_id=page_id,
                error=str(e),
                retryable=e.retryable,
            )
            raise llm_error_to_application_error(e) from e
        except Exception as e:
            logger.exception(
                "extract_page_entities_activity.exception", page_id=page_id, error=str(e)
            )
            raise

        if isinstance(result, Success):
            payload = result.unwrap()
            logger.info(
                "extract_page_entities_activity.success",
                page_id=page_id,
                entity_count=payload.get("entity_count", 0),
                status=payload.get("status"),
            )
            return payload

        error = result.failure()
        logger.error(
            "extract_page_entities_activity.failed",
            page_id=page_id,
            error_code=error.category,
            error_message=error.message,
        )
        raise failure_to_application_error(error)

    return extract_page_entities_activity


def create_aggregate_artifact_tags_activity(
    use_case: AggregateArtifactTagsUseCase,
) -> Callable[[str], dict]:
    """Create the aggregate_artifact_tags activity with injected dependencies."""

    @activity.defn(name="aggregate_artifact_tags")
    async def aggregate_artifact_tags_activity(artifact_id: str) -> dict:
        logger.info("aggregate_artifact_tags_activity.start", artifact_id=artifact_id)

        try:
            result = await use_case.execute(artifact_id=UUID(artifact_id))
        except LLMError as e:
            logger.error(  # noqa: TRY400 -- expected/typed failure, no traceback needed
                "aggregate_artifact_tags_activity.llm_error",
                artifact_id=artifact_id,
                error=str(e),
                retryable=e.retryable,
            )
            raise llm_error_to_application_error(e) from e
        except Exception as e:
            logger.exception(
                "aggregate_artifact_tags_activity.exception",
                artifact_id=artifact_id,
                error=str(e),
            )
            raise

        if isinstance(result, Success):
            payload = result.unwrap()
            logger.info(
                "aggregate_artifact_tags_activity.success",
                artifact_id=artifact_id,
                tag_count=payload.get("tag_count", 0),
            )
            return payload

        error = result.failure()
        logger.error(
            "aggregate_artifact_tags_activity.failed",
            artifact_id=artifact_id,
            error_code=error.category,
            error_message=error.message,
        )
        raise failure_to_application_error(error)

    return aggregate_artifact_tags_activity
