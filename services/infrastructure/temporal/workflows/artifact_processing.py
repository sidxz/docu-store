"""Artifact processing workflow (toy implementation).

This workflow orchestrates the processing of an artifact through a workflow
of activities. The structure follows the choreography of:

1. Extract metadata from artifact
2. Process through ML/LLM workflow
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
from uuid import UUID  # noqa: TC003  # Needed at runtime for Temporal workflow decorator

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities safely using Temporal's passthrough mechanism
# This avoids sandbox restrictions on imports with side effects
with workflow.unsafe.imports_passed_through():
    from infrastructure.temporal.activities.artifact_activities import (
        log_mime_type_activity,
        log_storage_location_activity,
    )


@workflow.defn
class ProcessArtifactWorkflow:
    """Orchestrates the long-running artifact processing workflow.

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
        """Execute the artifact processing workflow.

        Args:
            artifact_id: Unique identifier of the artifact
            storage_location: Path where artifact is stored
            mime_type: MIME type of the artifact

        Returns:
            Completion status message

        Raises:
            Will propagate activity failures after exhausting retries

        """
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

        return f"Artifact {artifact_id} workflow completed: {mime_result} | {location_result}"
