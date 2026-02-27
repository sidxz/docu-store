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
import os
import signal

import structlog
from eventsourcing.application import Application
from eventsourcing.projection import ApplicationSubscription

from application.workflow_use_cases.log_artifcat_sample_use_case import LogArtifactSampleUseCase
from application.workflow_use_cases.trigger_compound_extraction_use_case import (
    TriggerCompoundExtractionUseCase,
)
from application.workflow_use_cases.trigger_embedding_use_case import TriggerEmbeddingUseCase
from application.workflow_use_cases.trigger_page_summarization_use_case import (
    TriggerPageSummarizationUseCase,
)
from application.workflow_use_cases.trigger_smiles_embedding_use_case import (
    TriggerSmilesEmbeddingUseCase,
)
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from infrastructure.di.container import create_container
from infrastructure.lib.pipeline_worker_tracking import PipelineWorkerTracking
from infrastructure.logging import setup_logging

setup_logging()
logger = structlog.get_logger()


async def run(worker_name: str = "pipeline_worker") -> None:  # noqa: C901, PLR0912, PLR0915
    """Run the workflow orchestration worker.

    Subscribes to ArtifactCreated events from EventStoreDB and starts
    Temporal workflows to process each artifact.

    Args:
        worker_name: Unique name for this worker instance. Each distinct name
            maintains its own checkpoint in MongoDB, so multiple workers with
            different names process the event stream independently.

    Tracking:
    - Stores last processed event in MongoDB to resume from that point
    - Ensures events are only processed once across restarts (per worker_name)

    """
    container = create_container()
    app = container[Application]

    log_artifact_sample_use_case = container[LogArtifactSampleUseCase]
    trigger_compound_extraction_use_case = container[TriggerCompoundExtractionUseCase]
    trigger_embedding_use_case = container[TriggerEmbeddingUseCase]
    trigger_smiles_embedding_use_case = container[TriggerSmilesEmbeddingUseCase]
    trigger_page_summarization_use_case = container[TriggerPageSummarizationUseCase]

    # Setup signal handlers
    def handle_signal(signum: int, _frame: object) -> None:
        logger.info("pipeline_worker_signal_received", signum=signum)
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Topics we're interested in
    topics = [
        f"{Artifact.Created.__module__}:{Artifact.Created.__qualname__}",
        f"{Page.Created.__module__}:{Page.Created.__qualname__}",
        f"{Page.TextMentionUpdated.__module__}:{Page.TextMentionUpdated.__qualname__}",
        f"{Page.CompoundMentionsUpdated.__module__}:{Page.CompoundMentionsUpdated.__qualname__}",
        f"{Page.TextEmbeddingGenerated.__module__}:{Page.TextEmbeddingGenerated.__qualname__}",
    ]

    logger.info("pipeline_worker_started", worker_name=worker_name, topics=topics)

    pipeline_tracking = PipelineWorkerTracking(worker_name=worker_name)

    try:
        # Get last processed event position from our own independent checkpoint
        max_tracking_id = pipeline_tracking.get_position()
        if max_tracking_id is not None:
            logger.info("pipeline_worker_resuming", last_position=max_tracking_id)
        else:
            logger.info("pipeline_worker_starting_from_beginning")

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

                        if isinstance(domain_event, Page.Created):
                            logger.info(
                                "pipeline_page_created_event_received",
                                page_id=str(domain_event.originator_id),
                                tracking_id=tracking.notification_id,
                            )

                            await trigger_compound_extraction_use_case.execute(
                                page_id=domain_event.originator_id,
                            )

                            logger.info(
                                "pipeline_compound_extraction_workflow_triggered",
                                page_id=str(domain_event.originator_id),
                                tracking_id=tracking.notification_id,
                            )

                        elif isinstance(domain_event, Artifact.Created):
                            logger.info(
                                "pipeline_artifact_created_event_received",
                                artifact_id=str(domain_event.originator_id),
                                storage_location=domain_event.storage_location,
                                tracking_id=tracking.notification_id,
                            )

                            await log_artifact_sample_use_case.execute(
                                domain_event.originator_id,
                                storage_location=domain_event.storage_location,
                            )

                            logger.info(
                                "pipeline_workflow_triggered",
                                artifact_id=str(domain_event.originator_id),
                                tracking_id=tracking.notification_id,
                            )

                        elif isinstance(domain_event, Page.TextMentionUpdated):
                            if domain_event.text_mention is not None:
                                logger.info(
                                    "pipeline_text_mention_updated",
                                    page_id=str(domain_event.originator_id),
                                    tracking_id=tracking.notification_id,
                                )

                                await trigger_embedding_use_case.execute(
                                    page_id=domain_event.originator_id,
                                )

                                logger.info(
                                    "pipeline_embedding_workflow_triggered",
                                    page_id=str(domain_event.originator_id),
                                    tracking_id=tracking.notification_id,
                                )

                        elif isinstance(domain_event, Page.TextEmbeddingGenerated):
                            logger.info(
                                "pipeline_text_embedding_generated",
                                page_id=str(domain_event.originator_id),
                                tracking_id=tracking.notification_id,
                            )

                            await trigger_page_summarization_use_case.execute(
                                page_id=domain_event.originator_id,
                            )

                            logger.info(
                                "pipeline_summarization_workflow_triggered",
                                page_id=str(domain_event.originator_id),
                                tracking_id=tracking.notification_id,
                            )

                        elif isinstance(domain_event, Page.CompoundMentionsUpdated):
                            logger.info(
                                "pipeline_compound_mentions_updated",
                                page_id=str(domain_event.originator_id),
                                tracking_id=tracking.notification_id,
                            )

                            await trigger_smiles_embedding_use_case.execute(
                                page_id=domain_event.originator_id,
                            )

                            logger.info(
                                "pipeline_smiles_embedding_workflow_triggered",
                                page_id=str(domain_event.originator_id),
                                tracking_id=tracking.notification_id,
                            )

                        pipeline_tracking.save_position(tracking.notification_id)

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
    """Run the workflow worker in synchronous mode.

    Worker name can be set via the PIPELINE_WORKER_NAME environment variable.
    Defaults to "pipeline_worker".
    """
    worker_name = os.environ.get("PIPELINE_WORKER_NAME", "pipeline_worker")
    asyncio.run(run(worker_name=worker_name))


if __name__ == "__main__":
    run_sync()
