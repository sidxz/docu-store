"""Temporal workflow for batch re-embedding summary vectors for an artifact."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="BatchReEmbedSummariesWorkflow")
class BatchReEmbedSummariesWorkflow:
    """Batch re-embed all summary embeddings (page + artifact) for an artifact."""

    @workflow.run
    async def run(self, artifact_id: str) -> dict:
        workflow.logger.info(
            f"Batch re-embed summaries workflow started for artifact_id={artifact_id}",
        )

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(seconds=60),
            maximum_attempts=2,
            backoff_coefficient=2.0,
        )

        result = await workflow.execute_activity(
            "batch_reembed_summaries",
            artifact_id,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry_policy,
        )

        workflow.logger.info(
            f"Batch re-embed summaries workflow completed for artifact_id={artifact_id}, result={result}",
        )

        return result
