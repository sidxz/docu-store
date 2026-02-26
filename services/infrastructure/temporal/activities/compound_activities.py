from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.compound_use_cases import ExtractCompoundMentionsUseCase

logger = structlog.get_logger()


def create_extract_compound_mentions_activity(
    use_case: ExtractCompoundMentionsUseCase,
) -> Callable[[str], dict]:
    """Create the extract_compound_mentions activity with injected dependencies."""

    @activity.defn(name="extract_compound_mentions")
    async def extract_compound_mentions_activity(page_id: str) -> dict:
        logger.info("extract_compound_mentions_activity_start", page_id=page_id)

        try:
            page_uuid = UUID(page_id)
            result = await use_case.execute(page_id=page_uuid)
        except Exception as e:
            logger.exception(
                "extract_compound_mentions_activity_exception",
                page_id=page_id,
                error=str(e),
            )
            raise  # Re-raise for Temporal retry logic
        else:
            if isinstance(result, Success):
                page_response = result.unwrap()
                logger.info(
                    "extract_compound_mentions_activity_success",
                    page_id=page_id,
                    num_compounds=len(page_response.compound_mentions or []),
                )
                return {
                    "status": "success",
                    "page_id": page_id,
                    "num_compounds": len(page_response.compound_mentions or []),
                }

            error = result.failure()
            logger.error(
                "extract_compound_mentions_activity_failed",
                page_id=page_id,
                error_code=error.category,
                error_message=error.message,
            )
            return {
                "status": "failed",
                "page_id": page_id,
                "error_code": error.category,
                "error_message": error.message,
            }

    return extract_compound_mentions_activity
