from __future__ import annotations

import asyncio
from typing import Coroutine

import structlog

from application.ports.workflow_orchestrator import WorkflowOrchestrator
from domain.aggregates.blob import Blob

logger = structlog.get_logger()


class BlobUploadedPolicy:
    """Trigger workflows in response to uploaded blobs."""

    def __init__(self, workflow_orchestrator: WorkflowOrchestrator | None) -> None:
        self._workflow_orchestrator = workflow_orchestrator

    def handle(self, event: Blob.BlobUploaded) -> None:
        if not self._workflow_orchestrator:
            logger.info(
                "blob_uploaded_policy_no_orchestrator",
                blob_id=str(event.originator_id),
            )
            return

        blob_ref = event.blob_ref
        if blob_ref.mime_type != "application/pdf":
            logger.info(
                "blob_uploaded_policy_skipping_non_pdf",
                blob_id=str(event.originator_id),
                mime_type=blob_ref.mime_type,
            )
            return

        artifact_id = str(event.artifact_id) if event.artifact_id else None
        self._run_async(
            self._trigger_pdf_ingestion(
                storage_key=blob_ref.key,
                filename=blob_ref.filename,
                mime_type=blob_ref.mime_type,
                source_uri=event.source_uri,
                artifact_id=artifact_id,
            ),
        )

    async def _trigger_pdf_ingestion(
        self,
        *,
        storage_key: str,
        filename: str | None,
        mime_type: str | None,
        source_uri: str,
        artifact_id: str | None,
    ) -> None:
        try:
            workflow_id = await self._workflow_orchestrator.trigger_pdf_ingestion(
                storage_key=storage_key,
                filename=filename,
                mime_type=mime_type,
                source_uri=source_uri,
                artifact_id=artifact_id,
            )
            logger.info(
                "pdf_ingestion_workflow_triggered",
                workflow_id=workflow_id,
                storage_key=storage_key,
                artifact_id=artifact_id,
            )
        except Exception:
            logger.exception(
                "workflow_trigger_failed_upload_succeeded",
                storage_key=storage_key,
                artifact_id=artifact_id,
            )

    def _run_async(self, coro: Coroutine[object, object, object]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return

        task = loop.create_task(coro)
        task.add_done_callback(self._log_task_exception)

    @staticmethod
    def _log_task_exception(task: asyncio.Task[object]) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("blob_uploaded_policy_task_failed")
