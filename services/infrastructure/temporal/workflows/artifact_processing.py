"""Artifact processing workflow (toy implementation).

This workflow orchestrates the processing of an artifact through a pipeline
of activities. The structure follows the choreography of:

1. Extract metadata from artifact
2. Process through ML/LLM pipeline
3. Persist results back to domain

Currently this is a toy implementation that logs details.
It will be expanded to include:
- PDF parsing
- Page extraction
- LLM summarization
- Domain event emission to update aggregate state

NOTE: Workflows must be deterministic - they cannot use threading (locks), etc.
Logging is done in activities instead, not in workflows.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio.common import RetryPolicy

from infrastructure.temporal.activities.artifact_activities import (
    log_mime_type_activity,
    log_storage_location_activity,
)


class ProcessArtifactInput:
    """Input for the artifact processing workflow."""

    def __init__(self, artifact_id: UUID, storage_location: str, mime_type: str):
        self.artifact_id = artifact_id
        self.storage_location = storage_location
        self.mime_type = mime_type


@workflow.defn
class ProcessArtifactPipeline:
    """Orchestrates the long-running artifact processing pipeline.

    Workflow features:
    - Durable: Survives worker/service restarts
    - Idempotent: Same artifact_id = same execution (no duplicates)
    - Observable: Temporal UI shows all steps and timing
    - Resilient: Built-in retries and error handling

    Future: Will include PDF parsing, page extraction, LLM summarization
    """

    @workflow.run
    async def execute(
        self,
        artifact_id: UUID,
        storage_location: str,
        mime_type: str,
    ) -> str:
        """Execute the artifact processing pipeline.

        Args:
            artifact_id: Unique identifier of the artifact
            storage_location: Path where artifact is stored
            mime_type: MIME type of the artifact

        Returns:
            Completion status message

        Raises:
            Will propagate activity failures after exhausting retries

        """
        try:
            # Step 1: Log and validate MIME type
            mime_result = await workflow.execute_activity(
                log_mime_type_activity,
                mime_type,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            # Step 2: Log and validate storage location
            location_result = await workflow.execute_activity(
                log_storage_location_activity,
                storage_location,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            # Future steps would go here:
            # - parse_pdf_activity
            # - extract_first_page_activity
            # - llm_summarize_activity
            # - update_artifact_with_results_activity

            completion_msg = (
                f"✅ Artifact {artifact_id} pipeline completed: {mime_result} | {location_result}"
            )
            return completion_msg

        except Exception as e:
            error_msg = f"❌ Artifact {artifact_id} pipeline failed: {e}"
            raise
