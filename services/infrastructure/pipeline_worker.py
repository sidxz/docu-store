"""Pipeline orchestration worker using eventsourcing event subscription.

Similar to read_worker.py but for triggering long-running business processes.
Subscribes to domain events from EventStoreDB and starts Temporal workflows.

This worker is independent of the read model projector:
- read_worker.py → updates MongoDB read models
- pipeline_worker.py → starts Temporal workflows for business processing

Both subscribe to the same event stream but process events independently.
"""

from __future__ import annotations

import asyncio
import signal

import structlog
from eventsourcing.application import Application
from eventsourcing.projection import ApplicationSubscription

from application.ports.pipeline_orchestrator import PipelineOrchestrator
from domain.aggregates.artifact import Artifact
from infrastructure.di.container import create_container
from infrastructure.logging import setup_logging

setup_logging()
logger = structlog.get_logger()


async def run() -> None:
    """Run the pipeline orchestration worker.

    Subscribes to ArtifactCreated events from EventStoreDB and starts
    Temporal workflows to process each artifact.

    Event Flow:
    1. User uploads artifact → CreateArtifactUseCase saves to EventStoreDB
    2. ArtifactCreated event persisted
    3. This worker receives event via ApplicationSubscription
    4. Starts TemporalPipelineOrchestrator.start_artifact_processing_pipeline()
    5. Temporal workflow begins execution

    Tracking:
    - Stores last processed event in MongoDB to resume from that point
    - Ensures events are only processed once across restarts
    """
    container = create_container()
    app = container[Application]
    orchestrator = container[PipelineOrchestrator]

    # Setup signal handlers
    def handle_signal(signum: int, _frame: object) -> None:
        logger.info("pipeline_worker_signal_received", signum=signum)
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Topics we're interested in
    topics = [
        f"{Artifact.Created.__module__}:{Artifact.Created.__qualname__}",
    ]

    logger.info("pipeline_worker_started", topics=topics)

    try:
        # Get last processed event position from tracking
        # Use same approach as read_worker to track progress
        application_name = app.name
        max_tracking_id = None

        # Try to get max tracking ID from MongoDB (if available)
        try:
            from infrastructure.read_repositories.mongo_read_model_materializer import (
                MongoReadModelMaterializer,
            )

            materializer = container[MongoReadModelMaterializer]
            max_tracking_id = materializer.max_tracking_id(application_name)
            logger.info("pipeline_worker_resuming", last_position=max_tracking_id)
        except Exception as e:
            logger.warning(
                "pipeline_worker_no_tracking",
                error=str(e),
                note="Will process all events from beginning",
            )

        # Create subscription
        subscription_kwargs = {"topics": topics}
        if max_tracking_id is not None:
            subscription_kwargs["gt"] = max_tracking_id

        subscription = ApplicationSubscription(app, **subscription_kwargs)

        event_count = 0
        with subscription:
            try:
                for domain_event, tracking in subscription:
                    try:
                        event_count += 1

                        if isinstance(domain_event, Artifact.Created):
                            logger.info(
                                "pipeline_artifact_created_event_received",
                                artifact_id=str(domain_event.originator_id),
                                storage_location=domain_event.storage_location,
                                tracking_id=tracking.notification_id,
                            )

                            # Start the Temporal workflow
                            await orchestrator.start_artifact_processing_pipeline(
                                artifact_id=domain_event.originator_id,
                                storage_location=domain_event.storage_location,
                            )

                            logger.info(
                                "pipeline_workflow_triggered",
                                artifact_id=str(domain_event.originator_id),
                                tracking_id=tracking.notification_id,
                            )

                    except Exception:
                        logger.exception(
                            "pipeline_event_processing_error",
                            event_type=type(domain_event).__name__,
                            tracking_id=tracking.notification_id,
                        )
                        # Don't re-raise - continue processing other events
                        logger.warning("pipeline_continuing_after_error")

            except StopIteration:
                logger.info("pipeline_subscription_stopped")
            finally:
                logger.info("pipeline_subscription_closed", events_processed=event_count)

    except KeyboardInterrupt:
        logger.info("pipeline_worker_interrupted")
    except Exception:
        logger.exception("pipeline_worker_error")
        raise
    finally:
        logger.info("pipeline_worker_stopped")


def run_sync() -> None:
    """Synchronous entry point for the pipeline worker."""
    asyncio.run(run())


if __name__ == "__main__":
    run_sync()
