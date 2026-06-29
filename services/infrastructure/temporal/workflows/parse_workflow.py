"""Durable parse workflow for artifact ingestion."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ParseArtifactWorkflow")
class ParseArtifactWorkflow:
    """Durable parse of an artifact into its structured document + Pages."""

    @workflow.run
    async def run(self, artifact_id: str) -> dict:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(seconds=60),
            maximum_attempts=3,
            backoff_coefficient=2.0,
        )
        result = await workflow.execute_activity(
            "parse_artifact",
            artifact_id,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry_policy,
        )
        workflow.logger.info(f"Parse workflow completed for artifact_id={artifact_id}")
        return result
