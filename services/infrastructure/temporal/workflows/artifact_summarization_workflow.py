from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ArtifactSummarizationWorkflow")
class ArtifactSummarizationWorkflow:
    """Temporal workflow for generating an LLM summary of an entire artifact.

    Runs the sliding-window summarization chain over all page summaries.
    Timeout is longer than the page workflow because it makes multiple LLM calls
    (one per batch + synthesis + refinement).
    """

    @workflow.run
    async def run(self, artifact_id: str) -> dict:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(seconds=120),
            maximum_attempts=3,
            backoff_coefficient=2.0,
        )

        result = await workflow.execute_activity(
            "summarize_artifact",
            artifact_id,
            start_to_close_timeout=timedelta(minutes=60),
            retry_policy=retry_policy,
        )

        workflow.logger.info(
            f"Artifact summarization workflow completed for artifact_id={artifact_id}, result={result}",
        )

        return result
