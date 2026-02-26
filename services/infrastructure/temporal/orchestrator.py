"""Temporal implementation of the WorkflowOrchestrator port.

This is the infrastructure layer implementation that knows about Temporal.
The domain and application layers only depend on the WorkflowOrchestrator port.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from uuid import UUID
from temporalio.client import Client

from application.ports.workflow_orchestrator import WorkflowOrchestrator
from infrastructure.config import settings
from infrastructure.temporal.workflows.artifact_processing import ProcessArtifactWorkflow

logger = structlog.get_logger()


class TemporalWorkflowOrchestrator(WorkflowOrchestrator):
    """Orchestrates artifact processing pipelines using Temporal.

    Responsibilities:
    - Connect to Temporal server
    - Start workflows with appropriate IDs
    - Handle workflow lifecycle
    """

    def __init__(self, client: Client | None = None) -> None:
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

    async def start_artifact_processing_workflow(
        self,
        artifact_id: UUID,
        storage_location: str,
    ) -> None:
        """Start a workflow to process an artifact.

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
            # TODO(@sidxz): get mime_type from artifact aggregate (#123)  # noqa: FIX002
            mime_type = "application/pdf"

            handle = await self._client.start_workflow(
                ProcessArtifactWorkflow.execute,
                args=[artifact_id, storage_location, mime_type],
                id=workflow_id,
                task_queue="artifact_processing",
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

    async def start_embedding_workflow(
        self,
        page_id: UUID,
    ) -> None:
        """Start the embedding generation workflow for a page.

        Args:
            page_id: Unique identifier of the page to generate embeddings for

        """
        await self._ensure_client()

        workflow_id = f"embedding-{page_id}"

        try:
            await self._client.start_workflow(
                "GeneratePageEmbeddingWorkflow",
                str(page_id),
                id=workflow_id,
                task_queue="artifact_processing",  # Same queue as other workflows
            )
            logger.info("embedding_workflow_started", page_id=str(page_id))
        except Exception as e:
            logger.exception(
                "failed_to_start_embedding_workflow", page_id=str(page_id), error=str(e),
            )

    async def start_compound_extraction_workflow(
        self,
        page_id: UUID,
    ) -> None:
        """Start the compound extraction workflow for a page.

        Args:
            page_id: Unique identifier of the page to extract compounds from

        """
        await self._ensure_client()

        workflow_id = f"compound-extraction-{page_id}"

        try:
            await self._client.start_workflow(
                "ExtractCompoundMentionsWorkflow",
                str(page_id),
                id=workflow_id,
                task_queue="artifact_processing",
            )
            logger.info("compound_extraction_workflow_started", page_id=str(page_id))
        except Exception as e:
            logger.exception(
                "failed_to_start_compound_extraction_workflow", page_id=str(page_id), error=str(e),
            )
