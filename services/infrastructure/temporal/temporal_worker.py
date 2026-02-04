"""Temporal worker that processes workflows triggered by blob uploads.

This worker follows the same pattern as read_worker.py but for Temporal workflow orchestration.
It uses eventsourcing's ApplicationSubscription to listen for events that should trigger workflows.

For the toy example, we use a simple notification mechanism rather than complex event sourcing,
since blobs are temporary and don't have their own aggregates.
"""

from __future__ import annotations

import asyncio
import signal
from uuid import uuid4

import structlog
from temporalio.client import Client
from temporalio.worker import Worker

from application.use_cases.artifact_use_cases import CreateArtifactWithTitleUseCase
from application.use_cases.blob_use_cases import ExtractPdfContentUseCase
from infrastructure.di.container import create_container
from infrastructure.logging import setup_logging
from infrastructure.temporal.activities.pdf_processing_activities import (
    PdfProcessingActivities,
)
from infrastructure.temporal.workflows.pdf_ingestion_workflow import (
    PdfIngestionInput,
    PdfIngestionWorkflow,
)

setup_logging()

logger = structlog.get_logger()


class TemporalWorkerService:
    """Service that runs Temporal worker for workflow execution."""

    def __init__(
        self,
        temporal_host: str = "localhost:7233",
        task_queue: str = "docu-store-task-queue",
    ) -> None:
        self.temporal_host = temporal_host
        self.task_queue = task_queue
        self.client: Client | None = None
        self.worker: Worker | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the Temporal worker."""
        logger.info(
            "temporal_worker_starting",
            host=self.temporal_host,
            task_queue=self.task_queue,
        )

        # Connect to Temporal server
        self.client = await Client.connect(self.temporal_host)
        logger.info("temporal_client_connected")

        # Get use cases from DI container
        container = create_container()

        # Create activity instances with injected dependencies
        pdf_activities = PdfProcessingActivities(
            extract_pdf_content_use_case=container[ExtractPdfContentUseCase],
            create_artifact_with_title_use_case=container[CreateArtifactWithTitleUseCase],
        )

        # Create worker with workflows and activities
        self.worker = Worker(
            self.client,
            task_queue=self.task_queue,
            workflows=[PdfIngestionWorkflow],
            activities=[
                pdf_activities.check_if_pdf,
                pdf_activities.extract_pdf_first_page_content,
                pdf_activities.create_artifact_with_title,
            ],
        )
        logger.info("temporal_worker_created")

        # Run the worker
        logger.info("temporal_worker_running")
        await self.worker.run()

    async def stop(self) -> None:
        """Stop the Temporal worker."""
        logger.info("temporal_worker_stopping")
        self._stop_event.set()
        if self.worker:
            await self.worker.shutdown()
        logger.info("temporal_worker_stopped")

    async def trigger_pdf_ingestion_workflow(
        self,
        storage_key: str,
        filename: str | None,
        mime_type: str | None,
        source_uri: str,
        artifact_id: str | None = None,
    ) -> str:
        """Trigger a PDF ingestion workflow.

        This method can be called directly to start a workflow, or can be triggered
        by events from the event store.

        Args:
            storage_key: Storage key of the uploaded blob
            filename: Original filename
            mime_type: MIME type of the blob
            source_uri: Source URI for the document
            artifact_id: Optional artifact ID (generated if not provided)

        Returns:
            Workflow ID

        """
        if self.client is None:
            msg = "Temporal client not initialized. Call start() first."
            raise RuntimeError(msg)

        # Generate artifact ID if not provided
        if artifact_id is None:
            artifact_id = str(uuid4())

        workflow_id = f"pdf-ingestion-{artifact_id}"

        logger.info(
            "triggering_pdf_ingestion_workflow",
            workflow_id=workflow_id,
            storage_key=storage_key,
            filename=filename,
        )

        # Start the workflow
        await self.client.start_workflow(
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

        logger.info("pdf_ingestion_workflow_triggered", workflow_id=workflow_id)
        return workflow_id


async def run_worker() -> None:
    """Run the Temporal worker service.

    This is the main entry point for the Temporal worker process.
    """
    worker_service = TemporalWorkerService()

    def handle_signal(signum: int, _frame: object) -> None:
        logger.info("temporal_worker_signal_received", signum=signum)
        task = asyncio.create_task(worker_service.stop())
        # Store task reference to prevent garbage collection
        task.add_done_callback(lambda _: None)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        await worker_service.start()
    except KeyboardInterrupt:
        logger.info("temporal_worker_interrupted")
    except Exception:
        logger.exception("temporal_worker_error")
        raise
    finally:
        await worker_service.stop()
        logger.info("temporal_worker_shutdown_complete")


def main() -> None:
    """Run the Temporal worker."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
