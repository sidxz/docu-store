from uuid import UUID

import structlog
from temporalio import activity

from application.use_cases.embedding_use_cases import GeneratePageEmbeddingUseCase

logger = structlog.get_logger()


@activity.defn(name="generate_page_embedding")
async def generate_page_embedding_activity(page_id: str) -> dict:
    """Temporal activity to generate and store a page embedding.

    This activity:
    1. Calls the GeneratePageEmbeddingUseCase
    2. Returns the result

    Note: Dependencies (use case) are injected via the worker context
    during worker initialization. See worker.py for details.

    Args:
        page_id: UUID of the page to generate embedding for

    Returns:
        Dictionary with embedding information or error details

    Raises:
        Exception: If embedding generation fails critically

    """
    logger.info("generate_page_embedding_activity_start", page_id=page_id)

    # Get use case from activity context (set during worker init)
    # This is a common pattern in Temporal for dependency injection
    use_case: GeneratePageEmbeddingUseCase = activity.info().heartbeat_details

    try:
        page_uuid = UUID(page_id)
        result = await use_case.execute(page_id=page_uuid, force_regenerate=False)

        if result.is_success():
            embedding_dto = result.value_or(None)
            logger.info(
                "generate_page_embedding_activity_success",
                page_id=page_id,
                embedding_id=str(embedding_dto.embedding_id),
            )
            return {
                "status": "success",
                "page_id": page_id,
                "embedding_id": str(embedding_dto.embedding_id),
                "model_name": embedding_dto.model_name,
                "dimensions": embedding_dto.dimensions,
            }
        error = result.failure()
        logger.error(
            "generate_page_embedding_activity_failed",
            page_id=page_id,
            error_code=error.code,
            error_message=error.message,
        )
        return {
            "status": "failed",
            "page_id": page_id,
            "error_code": error.code,
            "error_message": error.message,
        }

    except Exception as e:
        logger.error(
            "generate_page_embedding_activity_exception",
            page_id=page_id,
            error=str(e),
            exc_info=True,
        )
        # Re-raise for Temporal to handle retries
        raise


@activity.defn(name="log_embedding_generated")
async def log_embedding_generated_activity(result: dict) -> None:
    """Simple logging activity for embedding generation result.

    Args:
        result: Result dictionary from generate_page_embedding_activity

    """
    if result["status"] == "success":
        logger.info(
            "embedding_workflow_completed",
            page_id=result["page_id"],
            embedding_id=result.get("embedding_id"),
            model=result.get("model_name"),
        )
    else:
        logger.warning(
            "embedding_workflow_failed",
            page_id=result["page_id"],
            error=result.get("error_message"),
        )
