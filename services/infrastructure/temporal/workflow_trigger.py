"""Temporal implementation of the WorkflowOrchestrator port.

This adapter implements workflow orchestration using Temporal.io.
It could be swapped with other implementations (AWS Step Functions, etc.)
without changing the application layer.
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from temporalio.client import Client

from application.ports.workflow_orchestrator import WorkflowOrchestrator
from infrastructure.config import settings
from infrastructure.temporal.workflows.pdf_ingestion_workflow import (
    PdfIngestionInput,
    PdfIngestionWorkflow,
)

logger = structlog.get_logger()


class TemporalWorkflowOrchestrator(WorkflowOrchestrator):
    """Temporal implementation of WorkflowOrchestrator port.

    This adapter uses Temporal.io to orchestrate workflows.
    It implements the port defined in the application layer.
    """

    def __init__(
        self,
        temporal_host: str | None = None,
        task_queue: str | None = None,
    ) -> None:
        """Initialize the workflow trigger service.

        Args:
            temporal_host: Temporal server host (defaults to settings)
            task_queue: Task queue name (defaults to settings)

        """
        self.temporal_host = temporal_host or getattr(
            settings,
            "temporal_host",
            "localhost:7233",
        )
        self.task_queue = task_queue or getattr(
            settings,
            "temporal_task_queue",
            "docu-store-task-queue",
        )
        self._client: Client | None = None

    async def _get_client(self) -> Client:
        """Get or create Temporal client connection.

        Returns:
            Connected Temporal client

        """
        if self._client is None:
            logger.info("connecting_to_temporal", host=self.temporal_host)
            self._client = await Client.connect(self.temporal_host)
            logger.info("temporal_client_connected")
        return self._client

    async def trigger_pdf_ingestion(
        self,
        storage_key: str,
        filename: str | None,
        mime_type: str | None,
        source_uri: str,
        artifact_id: str | None = None,
    ) -> str:
        """Trigger a PDF ingestion workflow.

        This method starts a Temporal workflow to process an uploaded PDF.
        The workflow will extract content from the PDF and create an artifact.

        Args:
            storage_key: Storage key of the uploaded blob
            filename: Original filename
            mime_type: MIME type of the blob
            source_uri: Source URI for the document
            artifact_id: Optional artifact ID (generated if not provided)

        Returns:
            Workflow ID

        Raises:
            Exception: If workflow trigger fails

        """
        client = await self._get_client()

        # Generate artifact ID if not provided
        if artifact_id is None:
            artifact_id = str(uuid4())

        workflow_id = f"pdf-ingestion-{artifact_id}"

        logger.info(
            "triggering_pdf_ingestion_workflow",
            workflow_id=workflow_id,
            storage_key=storage_key,
            filename=filename,
            mime_type=mime_type,
        )

        try:
            # Start the workflow (fire and forget)
            await client.start_workflow(
                PdfIngestionWorkflow.run,
                PdfIngestionInput(
                    artifact_id=artifact_id,
                    storage_key=storage_key,
                    filename=filename,
                    mime_type=mime_type,
                    source_uri=source_uri,
                ),
                id=workflow_id,
                task_queue=self.task_queue,
            )

            logger.info(
                "pdf_ingestion_workflow_triggered",
                workflow_id=workflow_id,
                artifact_id=artifact_id,
            )
            return workflow_id

        except Exception as e:
            logger.exception(
                "workflow_trigger_failed",
                workflow_id=workflow_id,
                error=str(e),
            )
            raise

    async def close(self) -> None:
        """Close the Temporal client connection."""
        if self._client:
            logger.info("closing_temporal_client")
            # Note: Temporal client doesn't have an explicit close method
            # The connection will be closed when the object is garbage collected
            self._client = None
