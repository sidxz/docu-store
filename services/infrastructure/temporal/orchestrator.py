"""Temporal implementation of the PipelineOrchestrator port.

This is the infrastructure layer implementation that knows about Temporal.
The domain and application layers only depend on the PipelineOrchestrator port.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from temporalio.client import Client

from application.ports.pipeline_orchestrator import PipelineOrchestrator
from infrastructure.config import settings
from infrastructure.temporal.workflows.artifact_processing import ProcessArtifactPipeline

logger = structlog.get_logger()


class TemporalPipelineOrchestrator(PipelineOrchestrator):
    """Orchestrates artifact processing pipelines using Temporal.

    Responsibilities:
    - Connect to Temporal server
    - Start workflows with appropriate IDs
    - Handle workflow lifecycle
    """

    def __init__(self, client: Client | None = None):
        """Initialize the Temporal orchestrator.

        Args:
            client: Temporal client. If None, will be initialized on first use.

        """
        self._client = client
        self._initialized = client is not None

    async def _ensure_client(self) -> None:
        """Lazy-initialize Temporal client on first use."""
        if not self._initialized:
            self._client = await Client.connect(settings.temporal_address)
            self._initialized = True

    async def start_artifact_processing_pipeline(
        self,
        artifact_id: UUID,
        storage_location: str,
    ) -> None:
        """Start a pipeline to process an artifact.

        Uses artifact_id as the workflow ID to ensure idempotency:
        - Same artifact_id always produces same workflow execution
        - Replaying the same event won't duplicate the workflow

        Args:
            artifact_id: Unique identifier of the artifact to process
            storage_location: Path/location where the artifact is stored

        """
        await self._ensure_client()

        try:
            # Workflow ID = artifact_id ensures idempotency
            # (same ID = same workflow, won't create duplicates)
            workflow_id = str(artifact_id)

            logger.info(
                "temporal_starting_workflow",
                workflow_id=workflow_id,
                artifact_id=str(artifact_id),
                storage_location=storage_location,
            )

            # Note: The artifact's mime_type is not available here.
            # In a real implementation, we'd either:
            # 1. Query the artifact repository to get mime_type
            # 2. Include mime_type in the event that triggered this
            # For now, we'll pass a placeholder
            mime_type = "application/pdf"  # TODO: get from artifact aggregate

            handle = await self._client.start_workflow(
                ProcessArtifactPipeline.execute,
                args=[artifact_id, storage_location, mime_type],
                id=workflow_id,
                task_queue="artifact_processing",
                # Optional: Set retention policy to clean up old workflows
                # retention_period=timedelta(days=7),
            )

            logger.info(
                "temporal_workflow_started",
                workflow_id=workflow_id,
                run_id=handle.id,
            )

        except Exception as e:
            logger.exception(
                "temporal_workflow_start_failed",
                artifact_id=str(artifact_id),
                error=str(e),
            )
            raise
