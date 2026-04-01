from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.embedding_use_cases import GeneratePageEmbeddingUseCase

logger = structlog.get_logger()


def create_generate_page_embedding_activity(
    use_case: GeneratePageEmbeddingUseCase,
) -> Callable[[str], dict]:
    """Create the generate_page_embedding activity with dependencies injected.

    Args:
        use_case: The GeneratePageEmbeddingUseCase instance

    Returns:
        The activity function with dependencies injected

    """

    @activity.defn(name="generate_page_embedding")
    async def generate_page_embedding_activity(input_data: dict | str) -> dict:
        """Temporal activity to generate and store a page embedding.

        This activity:
        1. Calls the GeneratePageEmbeddingUseCase
        2. Returns the result

        Args:
            input_data: Either a page_id string (legacy) or a dict with
                ``page_id`` and optional ``skip_sparse`` flag.

        Returns:
            Dictionary with embedding information or error details

        Raises:
            Exception: If embedding generation fails critically

        """
        if isinstance(input_data, str):
            page_id = input_data
            skip_sparse = False
        else:
            page_id = input_data["page_id"]
            skip_sparse = input_data.get("skip_sparse", False)

        logger.info(
            "generate_page_embedding_activity_start",
            page_id=page_id,
            skip_sparse=skip_sparse,
        )

        try:
            page_uuid = UUID(page_id)
            result = await use_case.execute(
                page_id=page_uuid,
                force_regenerate=True,
                skip_sparse=skip_sparse,
            )
        except Exception as e:
            logger.exception(
                "generate_page_embedding_activity_exception",
                page_id=page_id,
                error=str(e),
            )
            # Re-raise for Temporal to handle retries
            raise
        else:
            if isinstance(result, Success):
                embedding_dto = result.unwrap()
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
                error_code=error.category,
                error_message=error.message,
            )
            return {
                "status": "failed",
                "page_id": page_id,
                "error_code": error.category,
                "error_message": error.message,
            }

    return generate_page_embedding_activity


@activity.defn(name="log_embedding_generated")
async def log_embedding_generated_activity(result: dict) -> None:
    """Log the embedding generation result.

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
