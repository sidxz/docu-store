"""Temporal worker process for CPU/IO-bound workflows.

Handles embedding, compound extraction, SMILES embedding, summary embedding,
tag aggregation, and batch re-embedding. LLM-bound workflows (summarization,
NER, document metadata) run on a separate worker — see llm_worker.py.

Start with: python -m infrastructure.temporal.worker
"""

from __future__ import annotations

import asyncio

import structlog
from temporalio.client import Client
from temporalio.worker import Worker

from application.use_cases.aggregate_artifact_tags_use_case import AggregateArtifactTagsUseCase
from application.use_cases.batch_reembed_use_cases import (
    BatchReEmbedArtifactPagesUseCase,
    BatchReEmbedSmilesUseCase,
    BatchReEmbedSummariesUseCase,
)
from application.use_cases.compound_use_cases import ExtractCompoundMentionsUseCase
from application.use_cases.embedding_use_cases import GeneratePageEmbeddingUseCase
from application.use_cases.smiles_embedding_use_cases import EmbedCompoundSmilesUseCase
from application.use_cases.summary_embedding_use_cases import (
    EmbedArtifactSummaryUseCase,
    EmbedPageSummaryUseCase,
)
from infrastructure.config import settings
from infrastructure.di.container import create_container
from infrastructure.logging import setup_logging
from infrastructure.temporal.activities.artifact_activities import (
    log_mime_type_activity,
    log_storage_location_activity,
)
from infrastructure.temporal.activities.batch_reembed_activities import (
    create_batch_reembed_artifact_pages_activity,
)
from infrastructure.temporal.activities.batch_reembed_smiles_activities import (
    create_batch_reembed_smiles_activity,
)
from infrastructure.temporal.activities.batch_reembed_summaries_activities import (
    create_batch_reembed_summaries_activity,
)
from infrastructure.temporal.activities.compound_activities import (
    create_extract_compound_mentions_activity,
)
from infrastructure.temporal.activities.embedding_activities import (
    create_generate_page_embedding_activity,
    log_embedding_generated_activity,
)
from infrastructure.temporal.activities.ner_activities import (
    create_aggregate_artifact_tags_activity,
)
from infrastructure.temporal.activities.smiles_embedding_activities import (
    create_embed_compound_smiles_activity,
)
from infrastructure.temporal.activities.summary_embedding_activities import (
    create_embed_artifact_summary_activity,
    create_embed_page_summary_activity,
)
from infrastructure.temporal.workflows.artifact_processing import ProcessArtifactWorkflow
from infrastructure.temporal.workflows.batch_reembed_smiles_workflow import (
    BatchReEmbedSmilesWorkflow,
)
from infrastructure.temporal.workflows.batch_reembed_summaries_workflow import (
    BatchReEmbedSummariesWorkflow,
)
from infrastructure.temporal.workflows.batch_reembed_workflow import (
    BatchReEmbedArtifactPagesWorkflow,
)
from infrastructure.temporal.workflows.compound_workflow import ExtractCompoundMentionsWorkflow
from infrastructure.temporal.workflows.embedding_workflow import GeneratePageEmbeddingWorkflow
from infrastructure.temporal.workflows.ner_workflow import (
    ArtifactTagAggregationWorkflow,
)
from infrastructure.temporal.workflows.smiles_embedding_workflow import EmbedCompoundSmilesWorkflow
from infrastructure.temporal.workflows.summary_embedding_workflow import (
    ArtifactSummaryEmbeddingWorkflow,
    PageSummaryEmbeddingWorkflow,
)

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

    # Ensure Qdrant collections exist (worker may start before the API)
    try:
        from application.ports.compound_vector_store import CompoundVectorStore
        from application.ports.summary_vector_store import SummaryVectorStore
        from application.ports.vector_store import VectorStore

        await container[VectorStore].ensure_collection_exists()
        await container[CompoundVectorStore].ensure_compound_collection_exists()
        await container[SummaryVectorStore].ensure_collection_exists()
        logger.info("qdrant_collections_initialized")
    except Exception as e:
        logger.warning("qdrant_collection_init_failed", error=str(e))

    # Resolve dependencies
    generate_embedding_use_case = container[GeneratePageEmbeddingUseCase]
    extract_compound_mentions_use_case = container[ExtractCompoundMentionsUseCase]
    embed_compound_smiles_use_case = container[EmbedCompoundSmilesUseCase]
    embed_page_summary_use_case = container[EmbedPageSummaryUseCase]
    embed_artifact_summary_use_case = container[EmbedArtifactSummaryUseCase]
    aggregate_artifact_tags_use_case = container[AggregateArtifactTagsUseCase]
    batch_reembed_use_case = container[BatchReEmbedArtifactPagesUseCase]
    batch_reembed_smiles_use_case = container[BatchReEmbedSmilesUseCase]
    batch_reembed_summaries_use_case = container[BatchReEmbedSummariesUseCase]

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
    embed_page_summary_activity = create_embed_page_summary_activity(
        use_case=embed_page_summary_use_case,
    )
    embed_artifact_summary_activity = create_embed_artifact_summary_activity(
        use_case=embed_artifact_summary_use_case,
    )
    aggregate_artifact_tags_activity = create_aggregate_artifact_tags_activity(
        use_case=aggregate_artifact_tags_use_case,
    )
    batch_reembed_activity = create_batch_reembed_artifact_pages_activity(
        use_case=batch_reembed_use_case,
    )
    batch_reembed_smiles_activity = create_batch_reembed_smiles_activity(
        use_case=batch_reembed_smiles_use_case,
    )
    batch_reembed_summaries_activity = create_batch_reembed_summaries_activity(
        use_case=batch_reembed_summaries_use_case,
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
            PageSummaryEmbeddingWorkflow,
            ArtifactSummaryEmbeddingWorkflow,
            ArtifactTagAggregationWorkflow,
            BatchReEmbedArtifactPagesWorkflow,
            BatchReEmbedSmilesWorkflow,
            BatchReEmbedSummariesWorkflow,
        ],
        activities=[
            log_mime_type_activity,
            log_storage_location_activity,
            generate_page_embedding_activity,
            log_embedding_generated_activity,
            extract_compound_mentions_activity,
            embed_compound_smiles_activity,
            embed_page_summary_activity,
            embed_artifact_summary_activity,
            aggregate_artifact_tags_activity,
            batch_reembed_activity,
            batch_reembed_smiles_activity,
            batch_reembed_summaries_activity,
        ],
        max_concurrent_activities=settings.temporal_max_concurrent_activities,
    )

    # Heartbeat reporter — reports GPU and model status to MongoDB
    from application.dtos.health_dtos import ModelStatus
    from application.ports.embedding_generator import EmbeddingGenerator
    from infrastructure.embeddings.chemberta_generator import ChemBertaEmbeddingGenerator
    from infrastructure.health.heartbeat_reporter import HeartbeatReporter

    embedding_gen = container[EmbeddingGenerator]
    chemberta_gen = container[ChemBertaEmbeddingGenerator]

    async def _check_text_embedding() -> ModelStatus:
        info = await embedding_gen.get_model_info()
        return ModelStatus(
            name="Text Embedding",
            loaded=True,
            device=str(info.get("device", "unknown")),
            model_name=str(info.get("model_name", "unknown")),
            inference_ok=True,
        )

    async def _check_chemberta() -> ModelStatus:
        info = await chemberta_gen.get_model_info()
        return ModelStatus(
            name="SMILES Embedding (ChemBERTa)",
            loaded=True,
            device=str(info.get("device", "unknown")),
            model_name=str(info.get("model_name", "unknown")),
            inference_ok=True,
        )

    reporter = HeartbeatReporter(
        mongo_uri=settings.mongo_uri,
        mongo_db=settings.mongo_db,
        worker_type="temporal_cpu",
        worker_name="Temporal CPU/IO Worker",
        interval_seconds=settings.worker_heartbeat_interval_seconds,
        model_info_providers=[_check_text_embedding, _check_chemberta],
    )

    logger.info("temporal_worker_started")

    try:
        await asyncio.gather(worker.run(), reporter.run_forever())
    except KeyboardInterrupt:
        logger.info("temporal_worker_interrupted")
    except Exception:
        logger.exception("temporal_worker_error")
        raise
    finally:
        logger.info("temporal_worker_stopped")


if __name__ == "__main__":
    asyncio.run(run())
