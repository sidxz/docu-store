from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="EmbedCompoundSmilesWorkflow")
class EmbedCompoundSmilesWorkflow:
    """Temporal workflow for generating ChemBERTa SMILES embeddings for a page.

    Runs the ChemBERTa encoder on all valid canonical SMILES from the page's
    compound_mentions and stores the resulting vectors in the compound Qdrant collection.
    """

    @workflow.run
    async def run(self, page_id: str) -> dict:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(seconds=60),
            maximum_attempts=3,
            backoff_coefficient=2.0,
        )

        result = await workflow.execute_activity(
            "embed_compound_smiles",
            page_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )

        workflow.logger.info(
            f"SMILES embedding workflow completed for page_id={page_id}, result={result}",
        )

        return result
