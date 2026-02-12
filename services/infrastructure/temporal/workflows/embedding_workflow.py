from datetime import timedelta

import structlog
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from infrastructure.temporal.activities.embedding_activities import (
        generate_page_embedding_activity,
        log_embedding_generated_activity,
    )

logger = structlog.get_logger()


@workflow.defn(name="GeneratePageEmbeddingWorkflow")
class GeneratePageEmbeddingWorkflow:
    """Temporal workflow for generating page embeddings.

    This workflow orchestrates the embedding generation process,
    ensuring durability and retry logic.

    Workflow steps:
    1. Generate the embedding using the embedding generator
    2. Store it in the vector store
    3. Update the domain aggregate
    4. Log completion

    The workflow ID should be based on page_id to ensure idempotency.
    """

    @workflow.run
    async def run(self, page_id: str) -> dict:
        """Execute the embedding generation workflow.

        Args:
            page_id: UUID string of the page to process

        Returns:
            Dictionary with workflow result

        """
        logger.info(
            "embedding_workflow_started", page_id=page_id, workflow_id=workflow.info().workflow_id
        )

        # Define retry policy for activities
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=3,
            backoff_coefficient=2.0,
        )

        # Step 1: Generate and store the embedding
        result = await workflow.execute_activity(
            generate_page_embedding_activity,
            page_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )

        # Step 2: Log the result
        await workflow.execute_activity(
            log_embedding_generated_activity,
            result,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        logger.info("embedding_workflow_completed", page_id=page_id, result=result)

        return result
