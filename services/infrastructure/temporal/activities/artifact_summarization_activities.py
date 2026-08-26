from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.summarization_use_cases import SummarizeArtifactUseCase
from domain.exceptions import LLMError
from infrastructure.temporal.activities.errors import (
    failure_to_application_error,
    llm_error_to_application_error,
)

logger = structlog.get_logger()


def create_summarize_artifact_activity(
    use_case: SummarizeArtifactUseCase,
) -> Callable[[str], dict]:
    """Create the summarize_artifact activity with injected dependencies."""

    @activity.defn(name="summarize_artifact")
    async def summarize_artifact_activity(artifact_id: str) -> dict:
        logger.info("summarize_artifact_activity.start", artifact_id=artifact_id)

        try:
            result = await use_case.execute(artifact_id=UUID(artifact_id))
        except LLMError as e:
            logger.error(  # noqa: TRY400 -- expected/typed failure, no traceback needed
                "summarize_artifact_activity.llm_error",
                artifact_id=artifact_id,
                error=str(e),
                retryable=e.retryable,
            )
            raise llm_error_to_application_error(e) from e
        except Exception as e:
            logger.exception(
                "summarize_artifact_activity.exception",
                artifact_id=artifact_id,
                error=str(e),
            )
            raise  # Re-raise for Temporal retry logic

        if isinstance(result, Success):
            summary = result.unwrap().summary_candidate
            summary_len = len(summary.summary or "") if summary else 0
            logger.info(
                "summarize_artifact_activity.success",
                artifact_id=artifact_id,
                summary_len=summary_len,
            )
            return {"status": "success", "artifact_id": artifact_id, "summary_len": summary_len}

        error = result.failure()
        logger.error(
            "summarize_artifact_activity.failed",
            artifact_id=artifact_id,
            error_code=error.category,
            error_message=error.message,
        )
        raise failure_to_application_error(error)

    return summarize_artifact_activity
