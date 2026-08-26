from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.extract_document_metadata_use_case import ExtractDocumentMetadataUseCase
from domain.exceptions import LLMError
from infrastructure.temporal.activities.errors import (
    failure_to_application_error,
    llm_error_to_application_error,
)

logger = structlog.get_logger()


def create_extract_document_metadata_activity(
    use_case: ExtractDocumentMetadataUseCase,
) -> Callable[[str, str], dict]:
    """Create the extract_document_metadata activity with injected dependencies."""

    @activity.defn(name="extract_document_metadata")
    async def extract_document_metadata_activity(artifact_id: str, page_id: str) -> dict:
        logger.info(
            "extract_document_metadata_activity.start",
            artifact_id=artifact_id,
            page_id=page_id,
        )

        try:
            result = await use_case.execute(artifact_id=UUID(artifact_id), page_id=UUID(page_id))
        except LLMError as e:
            logger.error(  # noqa: TRY400 -- expected/typed failure, no traceback needed
                "extract_document_metadata_activity.llm_error",
                artifact_id=artifact_id,
                page_id=page_id,
                error=str(e),
                retryable=e.retryable,
            )
            raise llm_error_to_application_error(e) from e
        except Exception as e:
            logger.exception(
                "extract_document_metadata_activity.exception",
                artifact_id=artifact_id,
                page_id=page_id,
                error=str(e),
            )
            raise

        if isinstance(result, Success):
            payload = result.unwrap()
            logger.info(
                "extract_document_metadata_activity.success",
                artifact_id=artifact_id,
                status=payload.get("status"),
                author_count=payload.get("author_count", 0),
            )
            return payload

        error = result.failure()
        logger.error(
            "extract_document_metadata_activity.failed",
            artifact_id=artifact_id,
            page_id=page_id,
            error_code=error.category,
            error_message=error.message,
        )
        raise failure_to_application_error(error)

    return extract_document_metadata_activity
