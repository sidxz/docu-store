"""Temporal LLM worker process.

Runs a Temporal worker dedicated to LLM-bound workflows (summarization, NER,
document metadata extraction). Separated from the main worker so that slow
LLM activities do not block CPU/IO-bound work (embedding, compound extraction).

Start with: python -m infrastructure.temporal.llm_worker
"""

from __future__ import annotations

import asyncio

import structlog
from temporalio.client import Client
from temporalio.worker import Worker

from application.use_cases.extract_document_metadata_use_case import ExtractDocumentMetadataUseCase
from application.use_cases.extract_page_entities_use_case import ExtractPageEntitiesUseCase
from application.use_cases.summarization_use_cases import (
    SummarizeArtifactUseCase,
    SummarizePageUseCase,
)
from infrastructure.config import settings
from infrastructure.di.container import create_container
from infrastructure.logging import setup_logging
from infrastructure.temporal.activities.artifact_summarization_activities import (
    create_summarize_artifact_activity,
)
from infrastructure.temporal.activities.document_metadata_activities import (
    create_extract_document_metadata_activity,
)
from infrastructure.temporal.activities.ner_activities import (
    create_extract_page_entities_activity,
)
from infrastructure.temporal.activities.summarization_activities import (
    create_summarize_page_activity,
)
from infrastructure.temporal.workflows.artifact_summarization_workflow import (
    ArtifactSummarizationWorkflow,
)
from infrastructure.temporal.workflows.document_metadata_workflow import (
    DocumentMetadataExtractionWorkflow,
)
from infrastructure.temporal.workflows.ner_workflow import NERExtractionWorkflow
from infrastructure.temporal.workflows.summarization_workflow import PageSummarizationWorkflow

setup_logging()
logger = structlog.get_logger()


async def run() -> None:
    """Run the Temporal LLM worker.

    This worker:
    1. Connects to Temporal server
    2. Polls for tasks from the LLM-specific task queue
    3. Executes LLM-bound workflows and activities
    """
    logger.info(
        "temporal_llm_worker_starting",
        address=settings.temporal_address,
        task_queue=settings.temporal_llm_task_queue,
        max_concurrent=settings.temporal_max_concurrent_llm_activities,
    )

    container = create_container()

    # Resolve dependencies
    summarize_page_use_case = container[SummarizePageUseCase]
    summarize_artifact_use_case = container[SummarizeArtifactUseCase]
    extract_page_entities_use_case = container[ExtractPageEntitiesUseCase]
    extract_document_metadata_use_case = container[ExtractDocumentMetadataUseCase]

    # Create activities with dependencies injected
    summarize_page_activity = create_summarize_page_activity(
        use_case=summarize_page_use_case,
    )
    summarize_artifact_activity = create_summarize_artifact_activity(
        use_case=summarize_artifact_use_case,
    )
    extract_page_entities_activity = create_extract_page_entities_activity(
        use_case=extract_page_entities_use_case,
    )
    extract_document_metadata_activity = create_extract_document_metadata_activity(
        use_case=extract_document_metadata_use_case,
    )

    client = await Client.connect(settings.temporal_address)

    worker = Worker(
        client,
        task_queue=settings.temporal_llm_task_queue,
        workflows=[
            PageSummarizationWorkflow,
            ArtifactSummarizationWorkflow,
            NERExtractionWorkflow,
            DocumentMetadataExtractionWorkflow,
        ],
        activities=[
            summarize_page_activity,
            summarize_artifact_activity,
            extract_page_entities_activity,
            extract_document_metadata_activity,
        ],
        max_concurrent_activities=settings.temporal_max_concurrent_llm_activities,
    )

    # Heartbeat reporter — no local ML models, just reports GPU/system info
    from infrastructure.health.heartbeat_reporter import HeartbeatReporter

    reporter = HeartbeatReporter(
        mongo_uri=settings.mongo_uri,
        mongo_db=settings.mongo_db,
        worker_type="temporal_llm",
        worker_name="Temporal LLM Worker",
        interval_seconds=settings.worker_heartbeat_interval_seconds,
    )

    logger.info("temporal_llm_worker_started")

    try:
        await asyncio.gather(worker.run(), reporter.run_forever())
    except KeyboardInterrupt:
        logger.info("temporal_llm_worker_interrupted")
    except Exception:
        logger.exception("temporal_llm_worker_error")
        raise
    finally:
        logger.info("temporal_llm_worker_stopped")


if __name__ == "__main__":
    asyncio.run(run())
