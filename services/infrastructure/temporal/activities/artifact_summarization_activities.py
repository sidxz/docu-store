from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.summarization_use_cases import SummarizeArtifactUseCase

logger = structlog.get_logger()


def create_summarize_artifact_activity(
    use_case: SummarizeArtifactUseCase,
) -> Callable[[str], dict]:
    """Create the summarize_artifact activity with injected dependencies."""

    @activity.defn(name="summarize_artifact")
    async def summarize_artifact_activity(artifact_id: str) -> dict:
        logger.info("summarize_artifact_activity.start", artifact_id=artifact_id)

        try:
            artifact_uuid = UUID(artifact_id)
            result = await use_case.execute(artifact_id=artifact_uuid)
        except Exception as e:
            logger.exception(
                "summarize_artifact_activity.exception",
                artifact_id=artifact_id,
                error=str(e),
            )
            raise  # Re-raise for Temporal retry logic
        else:
            if isinstance(result, Success):
                artifact_response = result.unwrap()
                summary = artifact_response.summary_candidate
                logger.info(
                    "summarize_artifact_activity.success",
                    artifact_id=artifact_id,
                    summary_len=len(summary.summary or "") if summary else 0,
                )
                return {
                    "status": "success",
                    "artifact_id": artifact_id,
                    "summary_len": len(summary.summary or "") if summary else 0,
                }

            error = result.failure()
            logger.error(
                "summarize_artifact_activity.failed",
                artifact_id=artifact_id,
                error_code=error.category,
                error_message=error.message,
            )
            # Concurrency conflicts are retriable — raise so Temporal retries the activity.
            if error.category == "concurrency":
                msg = f"Concurrency conflict (will retry): {error.message}"
                raise RuntimeError(msg)
            return {
                "status": "failed",
                "artifact_id": artifact_id,
                "error_code": error.category,
                "error_message": error.message,
            }

    return summarize_artifact_activity
