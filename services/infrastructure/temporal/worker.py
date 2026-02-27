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

from application.use_cases.compound_use_cases import ExtractCompoundMentionsUseCase
from application.use_cases.embedding_use_cases import GeneratePageEmbeddingUseCase
from application.use_cases.smiles_embedding_use_cases import EmbedCompoundSmilesUseCase
from application.use_cases.summarization_use_cases import SummarizeArtifactUseCase, SummarizePageUseCase
from infrastructure.config import settings
from infrastructure.di.container import create_container
from infrastructure.logging import setup_logging
from infrastructure.temporal.activities.artifact_activities import (
    log_mime_type_activity,
    log_storage_location_activity,
)
from infrastructure.temporal.activities.compound_activities import (
    create_extract_compound_mentions_activity,
)
from infrastructure.temporal.activities.embedding_activities import (
    create_generate_page_embedding_activity,
    log_embedding_generated_activity,
)
from infrastructure.temporal.activities.smiles_embedding_activities import (
    create_embed_compound_smiles_activity,
)
from infrastructure.temporal.activities.artifact_summarization_activities import (
    create_summarize_artifact_activity,
)
from infrastructure.temporal.activities.summarization_activities import (
    create_summarize_page_activity,
)
from infrastructure.temporal.workflows.artifact_processing import ProcessArtifactWorkflow
from infrastructure.temporal.workflows.compound_workflow import ExtractCompoundMentionsWorkflow
from infrastructure.temporal.workflows.embedding_workflow import GeneratePageEmbeddingWorkflow
from infrastructure.temporal.workflows.smiles_embedding_workflow import EmbedCompoundSmilesWorkflow
from infrastructure.temporal.workflows.artifact_summarization_workflow import (
    ArtifactSummarizationWorkflow,
)
from infrastructure.temporal.workflows.summarization_workflow import PageSummarizationWorkflow

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

    # Initialize DI container
    container = create_container()

    # Resolve dependencies
    generate_embedding_use_case = container[GeneratePageEmbeddingUseCase]
    extract_compound_mentions_use_case = container[ExtractCompoundMentionsUseCase]
    embed_compound_smiles_use_case = container[EmbedCompoundSmilesUseCase]
    summarize_page_use_case = container[SummarizePageUseCase]
    summarize_artifact_use_case = container[SummarizeArtifactUseCase]

    # Create activities with dependencies injected
    generate_page_embedding_activity = create_generate_page_embedding_activity(
        use_case=generate_embedding_use_case,
    )
    extract_compound_mentions_activity = create_extract_compound_mentions_activity(
        use_case=extract_compound_mentions_use_case,
    )
    embed_compound_smiles_activity = create_embed_compound_smiles_activity(
        use_case=embed_compound_smiles_use_case,
    )
    summarize_page_activity = create_summarize_page_activity(
        use_case=summarize_page_use_case,
    )
    summarize_artifact_activity = create_summarize_artifact_activity(
        use_case=summarize_artifact_use_case,
    )

    client = await Client.connect(settings.temporal_address)

    worker = Worker(
        client,
        task_queue="artifact_processing",
        workflows=[
            ProcessArtifactWorkflow,
            GeneratePageEmbeddingWorkflow,
            ExtractCompoundMentionsWorkflow,
            EmbedCompoundSmilesWorkflow,
            PageSummarizationWorkflow,
            ArtifactSummarizationWorkflow,
        ],
        activities=[
            log_mime_type_activity,
            log_storage_location_activity,
            generate_page_embedding_activity,
            log_embedding_generated_activity,
            extract_compound_mentions_activity,
            embed_compound_smiles_activity,
            summarize_page_activity,
            summarize_artifact_activity,
        ],
        max_concurrent_activities=settings.temporal_max_concurrent_activities,
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
