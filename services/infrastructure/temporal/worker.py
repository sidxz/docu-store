"""Temporal worker process.

Runs the Temporal worker that executes workflows and activities.
This is the process that actually performs the work defined in workflows/activities.

Start with: python -m infrastructure.temporal.worker
"""

from __future__ import annotations

import asyncio

import structlog
from temporalio.client import Client
from temporalio.worker import Worker

from infrastructure.config import settings
from infrastructure.logging import setup_logging
from infrastructure.temporal.activities.artifact_activities import (
    log_mime_type_activity,
    log_storage_location_activity,
)
from infrastructure.temporal.workflows.artifact_processing import ProcessArtifactPipeline

setup_logging()
logger = structlog.get_logger()


async def run() -> None:
    """Run the Temporal worker.

    This worker:
    1. Connects to Temporal server
    2. Polls for tasks from the "artifact_processing" task queue
    3. Executes workflows and activities as they come in
    """
    logger.info("temporal_worker_starting", address=settings.temporal_address)

    client = await Client.connect(settings.temporal_address)

    worker = Worker(
        client,
        task_queue="artifact_processing",
        workflows=[ProcessArtifactPipeline],
        activities=[
            log_mime_type_activity,
            log_storage_location_activity,
            # Future activities will be added here
        ],
    )

    logger.info("temporal_worker_started")

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("temporal_worker_interrupted")
    except Exception:
        logger.exception("temporal_worker_error")
        raise
    finally:
        logger.info("temporal_worker_stopped")


if __name__ == "__main__":
    asyncio.run(run())
