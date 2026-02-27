from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="PageSummarizationWorkflow")
class PageSummarizationWorkflow:
    """Temporal workflow for generating an LLM summary of a single page.

    LLM calls can be slow (5–30 s) and occasionally fail — the activity
    timeout and retry policy are set accordingly.
    """

    @workflow.run
    async def run(self, page_id: str) -> dict:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(seconds=120),
            maximum_attempts=3,
            backoff_coefficient=2.0,
        )

        result = await workflow.execute_activity(
            "summarize_page",
            page_id,
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=retry_policy,
        )

        workflow.logger.info(
            f"Page summarization workflow completed for page_id={page_id}, result={result}",
        )

        return result
