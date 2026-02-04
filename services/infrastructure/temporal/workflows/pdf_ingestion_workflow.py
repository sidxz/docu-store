"""Temporal workflow for PDF ingestion and processing.

This workflow orchestrates the process of:
1. Checking if uploaded blob is a PDF
2. Extracting content from the first page
3. Creating an artifact with the extracted text as title

Following DDD principles, workflows live in infrastructure layer and coordinate
activities that call application use cases for business logic.
"""

from dataclasses import dataclass
from datetime import timedelta

import structlog
from temporalio import workflow

# Import activity stubs - Temporal requires using these for type-safe activity calls
with workflow.unsafe.imports_passed_through():
    from infrastructure.temporal.activities.pdf_processing_activities import (
        ExtractedContent,
        PdfProcessingActivities,
    )

logger = structlog.get_logger()


@dataclass
class PdfIngestionInput:
    """Input for PDF ingestion workflow."""

    artifact_id: str
    storage_key: str
    filename: str | None
    mime_type: str | None
    source_uri: str


@dataclass
class PdfIngestionResult:
    """Result of PDF ingestion workflow."""

    artifact_id: str | None
    processed: bool
    reason: str


@workflow.defn(name="pdf_ingestion_workflow")
class PdfIngestionWorkflow:
    """Workflow that processes uploaded PDFs and creates artifacts.

    This is a toy example demonstrating Temporal integration with event-sourced
    DDD application. In production, this would include:
    - Retry policies for transient failures
    - Compensation logic for rollbacks
    - More sophisticated error handling
    - Signals for cancellation
    """

    @workflow.run
    async def run(self, workflow_input: PdfIngestionInput) -> PdfIngestionResult:
        """Execute the PDF ingestion workflow.

        Args:
            workflow_input: Workflow input with blob information

        Returns:
            Result indicating success or failure

        """
        workflow.logger.info(
            "Starting PDF ingestion workflow",
            artifact_id=workflow_input.artifact_id,
            storage_key=workflow_input.storage_key,
            filename=workflow_input.filename,
        )

        # Step 1: Check if the blob is a PDF
        workflow.logger.info("Step 1: Checking if blob is PDF")
        is_pdf = await workflow.execute_activity(
            PdfProcessingActivities.check_if_pdf,
            args=[workflow_input.filename, workflow_input.mime_type],
            start_to_close_timeout=timedelta(seconds=10),
        )

        if not is_pdf:
            workflow.logger.info("Blob is not a PDF, skipping processing")
            return PdfIngestionResult(
                artifact_id=None,
                processed=False,
                reason="Not a PDF file",
            )

        workflow.logger.info("Blob is a PDF, proceeding with extraction")

        # Step 2: Extract first page content (first 20 words)
        workflow.logger.info("Step 2: Extracting first page content")
        try:
            extracted_content: ExtractedContent = await workflow.execute_activity(
                PdfProcessingActivities.extract_pdf_first_page_content,
                args=[workflow_input.storage_key, 20],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=workflow.RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=10),
                    maximum_attempts=3,
                ),
            )
            workflow.logger.info(
                "Content extracted successfully",
                word_count=extracted_content.word_count,
            )
        except Exception as e:  # noqa: BLE001
            # Broad exception catch is intentional for workflow fault tolerance
            workflow.logger.error("Failed to extract PDF content", error=str(e))
            return PdfIngestionResult(
                artifact_id=None,
                processed=False,
                reason=f"Content extraction failed: {e!s}",
            )

        # Step 3: Create artifact with extracted text as title
        workflow.logger.info("Step 3: Creating artifact with title")
        try:
            artifact_id = await workflow.execute_activity(
                PdfProcessingActivities.create_artifact_with_title,
                args=[
                    workflow_input.artifact_id,
                    workflow_input.storage_key,
                    workflow_input.filename,
                    workflow_input.source_uri,
                    extracted_content.text,
                ],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=workflow.RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=10),
                    maximum_attempts=3,
                ),
            )
            workflow.logger.info("Artifact created successfully", artifact_id=artifact_id)
        except Exception as e:  # noqa: BLE001
            # Broad exception catch is intentional for workflow fault tolerance
            workflow.logger.error("Failed to create artifact", error=str(e))
            return PdfIngestionResult(
                artifact_id=None,
                processed=False,
                reason=f"Artifact creation failed: {e!s}",
            )

        workflow.logger.info("PDF ingestion workflow completed successfully")
        return PdfIngestionResult(
            artifact_id=artifact_id,
            processed=True,
            reason="Successfully processed PDF and created artifact",
        )
