#!/usr/bin/env python
"""Demo script for Temporal PDF ingestion workflow.

This script demonstrates how to trigger the PDF ingestion workflow.
It uploads a sample PDF and triggers the workflow to process it.

Usage:
    python scripts/demo_temporal_pdf_workflow.py
"""

import asyncio
from uuid import uuid4

import structlog
from temporalio.client import Client

from infrastructure.logging import setup_logging
from infrastructure.temporal.workflows.pdf_ingestion_workflow import (
    PdfIngestionInput,
    PdfIngestionWorkflow,
)

setup_logging()
logger = structlog.get_logger()


async def demo_pdf_workflow() -> None:
    """Demonstrate the PDF ingestion workflow."""
    logger.info("Starting PDF ingestion workflow demo")

    # Configuration
    temporal_host = "localhost:7233"
    task_queue = "docu-store-task-queue"

    # Connect to Temporal
    logger.info("Connecting to Temporal", host=temporal_host)
    client = await Client.connect(temporal_host)
    logger.info("Connected to Temporal")

    # Create workflow input
    # In a real scenario, this would come from an uploaded blob
    artifact_id = str(uuid4())
    workflow_id = f"pdf-ingestion-demo-{artifact_id}"

    workflow_input = PdfIngestionInput(
        artifact_id=artifact_id,
        storage_key="artifacts/demo/sample.pdf",  # This should exist in your blob store
        filename="sample.pdf",
        mime_type="application/pdf",
        source_uri="https://example.com/sample.pdf",
    )

    logger.info(
        "Triggering workflow",
        workflow_id=workflow_id,
        artifact_id=artifact_id,
    )

    # Option 1: Execute and wait for result
    try:
        result = await client.execute_workflow(
            PdfIngestionWorkflow.run,
            workflow_input,
            id=workflow_id,
            task_queue=task_queue,
        )

        logger.info(
            "Workflow completed",
            result=result,
            processed=result.processed,
            reason=result.reason,
        )

        if result.processed:
            logger.info(
                "✅ Success! Artifact created",
                artifact_id=result.artifact_id,
            )
        else:
            logger.warning(
                "⚠️  Workflow completed but did not process",
                reason=result.reason,
            )

    except Exception as e:
        logger.error("❌ Workflow failed", error=str(e), error_type=type(e).__name__)
        raise

    logger.info("Demo completed")


async def demo_start_workflow_async() -> None:
    """Demonstrate starting a workflow asynchronously (fire and forget)."""
    logger.info("Starting async PDF ingestion workflow demo")

    temporal_host = "localhost:7233"
    task_queue = "docu-store-task-queue"

    client = await Client.connect(temporal_host)

    artifact_id = str(uuid4())
    workflow_id = f"pdf-ingestion-async-{artifact_id}"

    workflow_input = PdfIngestionInput(
        artifact_id=artifact_id,
        storage_key="artifacts/demo/sample.pdf",
        filename="sample.pdf",
        mime_type="application/pdf",
        source_uri="https://example.com/sample.pdf",
    )

    # Start workflow without waiting for result
    handle = await client.start_workflow(
        PdfIngestionWorkflow.run,
        workflow_input,
        id=workflow_id,
        task_queue=task_queue,
    )

    logger.info(
        "Workflow started (async)",
        workflow_id=workflow_id,
        run_id=handle.first_execution_run_id,
    )

    logger.info(
        "💡 View workflow in Temporal UI: http://localhost:8233/namespaces/default/workflows/%s",
        workflow_id,
    )

    # Optionally, wait for result later
    # result = await handle.result()


async def demo_query_workflow_status() -> None:
    """Demonstrate querying an existing workflow's status."""
    logger.info("Querying workflow status demo")

    temporal_host = "localhost:7233"
    workflow_id = input("Enter workflow ID to query: ").strip()

    if not workflow_id:
        logger.error("No workflow ID provided")
        return

    client = await Client.connect(temporal_host)

    # Get workflow handle
    handle = client.get_workflow_handle(workflow_id)

    # Check if workflow is running
    try:
        description = await handle.describe()
        logger.info(
            "Workflow status",
            workflow_id=workflow_id,
            status=description.status,
        )

        # Get result if completed
        if description.status.name == "COMPLETED":
            result = await handle.result()
            logger.info("Workflow result", result=result)

    except Exception as e:
        logger.error("Failed to query workflow", error=str(e))


def main() -> None:
    """Main entry point."""
    print("\n" + "=" * 60)
    print("Temporal PDF Ingestion Workflow Demo")
    print("=" * 60)
    print("\nChoose an option:")
    print("1. Execute workflow and wait for result")
    print("2. Start workflow asynchronously (fire and forget)")
    print("3. Query existing workflow status")
    print("=" * 60)

    choice = input("\nEnter choice (1-3): ").strip()

    if choice == "1":
        asyncio.run(demo_pdf_workflow())
    elif choice == "2":
        asyncio.run(demo_start_workflow_async())
    elif choice == "3":
        asyncio.run(demo_query_workflow_status())
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
