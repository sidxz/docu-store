from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="DocumentMetadataExtractionWorkflow")
class DocumentMetadataExtractionWorkflow:
    """Extract title, authors, and date from a document's first page.

    Uses GLiNER2 for fast structured extraction with LLM fallback.
    """

    @workflow.run
    async def run(self, artifact_id: str, page_id: str) -> dict:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(seconds=60),
            maximum_attempts=3,
            backoff_coefficient=2.0,
        )

        result = await workflow.execute_activity(
            "extract_document_metadata",
            args=[artifact_id, page_id],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )

        workflow.logger.info(
            f"Document metadata extraction completed for artifact_id={artifact_id}, result={result}",
        )
        return result
