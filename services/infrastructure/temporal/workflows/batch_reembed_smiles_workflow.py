"""Temporal workflow for batch re-embedding SMILES/compound vectors for an artifact."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="BatchReEmbedSmilesWorkflow")
class BatchReEmbedSmilesWorkflow:
    """Batch re-embed all compound SMILES embeddings for an artifact."""

    @workflow.run
    async def run(self, artifact_id: str) -> dict:
        workflow.logger.info(
            f"Batch re-embed SMILES workflow started for artifact_id={artifact_id}",
        )

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(seconds=60),
            maximum_attempts=2,
            backoff_coefficient=2.0,
        )

        result = await workflow.execute_activity(
            "batch_reembed_smiles",
            artifact_id,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry_policy,
        )

        workflow.logger.info(
            f"Batch re-embed SMILES workflow completed for artifact_id={artifact_id}, result={result}",
        )

        return result
