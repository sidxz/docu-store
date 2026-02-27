"""Temporal workflows for embedding page and artifact summaries."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=3,
    backoff_coefficient=2.0,
)


@workflow.defn(name="PageSummaryEmbeddingWorkflow")
class PageSummaryEmbeddingWorkflow:
    """Embed a page summary into the summary_embeddings Qdrant collection."""

    @workflow.run
    async def run(self, page_id: str) -> dict:
        result = await workflow.execute_activity(
            "embed_page_summary",
            page_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY_POLICY,
        )
        workflow.logger.info(
            f"PageSummaryEmbeddingWorkflow completed page_id={page_id} result={result}",
        )
        return result


@workflow.defn(name="ArtifactSummaryEmbeddingWorkflow")
class ArtifactSummaryEmbeddingWorkflow:
    """Embed an artifact summary into the summary_embeddings Qdrant collection."""

    @workflow.run
    async def run(self, artifact_id: str) -> dict:
        result = await workflow.execute_activity(
            "embed_artifact_summary",
            artifact_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY_POLICY,
        )
        workflow.logger.info(
            f"ArtifactSummaryEmbeddingWorkflow completed artifact_id={artifact_id} result={result}",
        )
        return result
