from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ExtractCompoundMentionsWorkflow")
class ExtractCompoundMentionsWorkflow:
    """Temporal workflow for extracting chemical compound mentions from a page.

    Runs the CSER ML pipeline (YOLO detector + neural matcher + SMILES extractor)
    on the rendered page image and persists the results to the Page aggregate.
    The pipeline is slow, so the activity timeout is generous.
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
            "extract_compound_mentions",
            page_id,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=retry_policy,
        )

        workflow.logger.info(
            f"Compound extraction workflow completed for page_id={page_id}, result={result}"
        )

        return result
