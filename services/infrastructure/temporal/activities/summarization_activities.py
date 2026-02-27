from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.summarization_use_cases import SummarizePageUseCase

logger = structlog.get_logger()


def create_summarize_page_activity(
    use_case: SummarizePageUseCase,
) -> Callable[[str], dict]:
    """Create the summarize_page activity with injected dependencies."""

    @activity.defn(name="summarize_page")
    async def summarize_page_activity(page_id: str) -> dict:
        logger.info("summarize_page_activity.start", page_id=page_id)

        try:
            page_uuid = UUID(page_id)
            result = await use_case.execute(page_id=page_uuid)
        except Exception as e:
            logger.exception(
                "summarize_page_activity.exception",
                page_id=page_id,
                error=str(e),
            )
            raise  # Re-raise for Temporal retry logic
        else:
            if isinstance(result, Success):
                page_response = result.unwrap()
                summary = page_response.summary_candidate
                logger.info(
                    "summarize_page_activity.success",
                    page_id=page_id,
                    summary_len=len(summary.summary or "") if summary else 0,
                )
                return {
                    "status": "success",
                    "page_id": page_id,
                    "summary_len": len(summary.summary or "") if summary else 0,
                }

            error = result.failure()
            logger.error(
                "summarize_page_activity.failed",
                page_id=page_id,
                error_code=error.category,
                error_message=error.message,
            )
            # Concurrency conflicts are retriable — raise so Temporal retries the activity.
            if error.category == "concurrency":
                raise RuntimeError(f"Concurrency conflict (will retry): {error.message}")
            return {
                "status": "failed",
                "page_id": page_id,
                "error_code": error.category,
                "error_message": error.message,
            }

    return summarize_page_activity
