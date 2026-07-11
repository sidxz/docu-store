from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ReconcileCompoundLabelsWorkflow")
class ReconcileCompoundLabelsWorkflow:
    """Reconcile CSER compound labels against NER compound_name tags for a page.

    Idempotent: the use case emits a corrected CompoundMentionsUpdated only when a
    label actually changes, so re-runs after the label is canonical are no-ops.
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
            "reconcile_compound_labels",
            page_id,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )

        workflow.logger.info(
            f"Compound-label reconciliation completed for page_id={page_id}, result={result}",
        )

        return result
