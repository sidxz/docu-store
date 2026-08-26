from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.summarization_use_cases import SummarizePageUseCase
from domain.exceptions import LLMError
from infrastructure.temporal.activities.errors import (
    failure_to_application_error,
    llm_error_to_application_error,
)

logger = structlog.get_logger()


def create_summarize_page_activity(
    use_case: SummarizePageUseCase,
) -> Callable[[str], dict]:
    """Create the summarize_page activity with injected dependencies."""

    @activity.defn(name="summarize_page")
    async def summarize_page_activity(page_id: str) -> dict:
        logger.info("summarize_page_activity.start", page_id=page_id)

        try:
            result = await use_case.execute(page_id=UUID(page_id))
        except LLMError as e:
            logger.error(  # noqa: TRY400 -- expected/typed failure, no traceback needed
                "summarize_page_activity.llm_error",
                page_id=page_id,
                error=str(e),
                retryable=e.retryable,
            )
            raise llm_error_to_application_error(e) from e
        except Exception as e:
            logger.exception("summarize_page_activity.exception", page_id=page_id, error=str(e))
            raise  # Re-raise for Temporal retry logic

        if isinstance(result, Success):
            summary = result.unwrap().summary_candidate
            summary_len = len(summary.summary or "") if summary else 0
            logger.info("summarize_page_activity.success", page_id=page_id, summary_len=summary_len)
            return {"status": "success", "page_id": page_id, "summary_len": summary_len}

        error = result.failure()
        logger.error(
            "summarize_page_activity.failed",
            page_id=page_id,
            error_code=error.category,
            error_message=error.message,
        )
        raise failure_to_application_error(error)

    return summarize_page_activity
