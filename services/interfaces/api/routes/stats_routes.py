"""Pipeline stats routes for admin monitoring."""

from collections import defaultdict
from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from lagom import Container
from sentinel_auth import RequestAuth
from temporalio.client import Client

from application.dtos.stats_dtos import (
    ActiveWorkflow,
    ChatLatencyStatsResponse,
    CitationFrequencyResponse,
    CollectionStats,
    FailedWorkflow,
    GroundingStatsResponse,
    KnowledgeGapsResponse,
    PipelineStatsResponse,
    SearchQualityStatsResponse,
    TokenUsageStatsResponse,
    VectorStatsResponse,
    WorkflowStatsResponse,
    WorkflowTypeStats,
)
from application.ports.analytics_read_model import AnalyticsReadModel
from application.ports.compound_vector_store import CompoundVectorStore
from application.ports.embedding_generator import EmbeddingGenerator
from application.ports.reranker import Reranker
from application.ports.summary_vector_store import SummaryVectorStore
from application.ports.vector_store import VectorStore
from infrastructure.config import settings
from infrastructure.embeddings.chemberta_generator import ChemBertaEmbeddingGenerator
from interfaces.dependencies import get_auth, get_container

logger = structlog.get_logger()

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/workflows", status_code=status.HTTP_200_OK)
async def get_workflow_stats(
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> WorkflowStatsResponse:
    """Get Temporal workflow execution statistics (admin only)."""
    if not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    logger.info("workflow_stats_requested")

    client = await Client.connect(settings.temporal_address)

    # --- Completed workflows: group by type, compute duration stats ---
    durations_by_type: dict[str, list[float]] = defaultdict(list)
    async for wf in client.list_workflows('ExecutionStatus = "Completed"'):
        if wf.workflow_type and wf.start_time and wf.close_time:
            duration = (wf.close_time - wf.start_time).total_seconds()
            durations_by_type[wf.workflow_type].append(duration)

    completed: list[WorkflowTypeStats] = []
    for wf_type, durations in sorted(durations_by_type.items()):
        durations.sort()
        count = len(durations)
        p95_idx = int(count * 0.95)
        completed.append(
            WorkflowTypeStats(
                workflow_type=wf_type,
                count=count,
                avg_duration_seconds=round(sum(durations) / count, 3),
                min_duration_seconds=round(durations[0], 3),
                max_duration_seconds=round(durations[-1], 3),
                p95_duration_seconds=round(durations[p95_idx], 3),
            ),
        )

    # --- Running workflows: count by type ---
    active_counts: dict[str, int] = defaultdict(int)
    async for wf in client.list_workflows('ExecutionStatus = "Running"'):
        if wf.workflow_type:
            active_counts[wf.workflow_type] += 1

    active = [
        ActiveWorkflow(workflow_type=wf_type, count=count)
        for wf_type, count in sorted(active_counts.items())
    ]

    # --- Failed workflows: last 10 (sorted client-side, no ORDER BY in query) ---
    all_failures: list[FailedWorkflow] = []
    async for wf in client.list_workflows('ExecutionStatus = "Failed"'):
        failure_message: str | None = None
        try:
            handle = client.get_workflow_handle(wf.id)
            desc = await handle.describe()
            if hasattr(desc, "failure") and desc.failure:
                failure_message = str(desc.failure)
        except Exception:
            failure_message = None

        all_failures.append(
            FailedWorkflow(
                workflow_id=wf.id,
                workflow_type=wf.workflow_type or "unknown",
                started_at=wf.start_time,
                closed_at=wf.close_time,
                failure_message=failure_message,
            ),
        )

    # Sort by start time descending, take last 10
    recent_failures = sorted(
        all_failures,
        key=lambda f: f.started_at or datetime.min,
        reverse=True,
    )[:10]

    logger.info(
        "workflow_stats_collected",
        completed_types=len(completed),
        active_types=len(active),
        failures=len(recent_failures),
    )

    return WorkflowStatsResponse(
        completed=completed,
        active=active,
        recent_failures=recent_failures,
    )


@router.get("/pipeline", status_code=status.HTTP_200_OK)
async def get_pipeline_stats(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> PipelineStatsResponse:
    """Get document pipeline processing statistics (admin only)."""
    if not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    logger.info("pipeline_stats_requested")

    from motor.motor_asyncio import AsyncIOMotorClient as _MongoClient

    mongo_client = container[_MongoClient]
    db = mongo_client[settings.mongo_db]
    pages = db[settings.mongo_pages_collection]
    artifacts = db[settings.mongo_artifacts_collection]

    pipeline = [
        {
            "$group": {
                "_id": None,
                "total_pages": {"$sum": 1},
                "with_text": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$ne": ["$text_mention", None]},
                                    {"$ne": ["$text_mention", ""]},
                                ],
                            },
                            1,
                            0,
                        ],
                    },
                },
                "with_summary": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$ne": ["$summary_candidate", None]},
                                    {
                                        "$ne": [
                                            {
                                                "$ifNull": [
                                                    "$summary_candidate.summary",
                                                    "",
                                                ],
                                            },
                                            "",
                                        ],
                                    },
                                ],
                            },
                            1,
                            0,
                        ],
                    },
                },
                "with_compounds": {
                    "$sum": {
                        "$cond": [
                            {
                                "$gt": [
                                    {"$size": {"$ifNull": ["$compound_mentions", []]}},
                                    0,
                                ],
                            },
                            1,
                            0,
                        ],
                    },
                },
                "with_tags": {
                    "$sum": {
                        "$cond": [
                            {
                                "$gt": [
                                    {"$size": {"$ifNull": ["$tag_mentions", []]}},
                                    0,
                                ],
                            },
                            1,
                            0,
                        ],
                    },
                },
            },
        },
    ]

    cursor = pages.aggregate(pipeline)
    result = await cursor.to_list(length=1)

    if result:
        stats = result[0]
        total_pages = stats["total_pages"]
        pages_with_text = stats["with_text"]
        pages_with_summary = stats["with_summary"]
        pages_with_compounds = stats["with_compounds"]
        pages_with_tags = stats["with_tags"]
    else:
        total_pages = 0
        pages_with_text = 0
        pages_with_summary = 0
        pages_with_compounds = 0
        pages_with_tags = 0

    total_artifacts = await artifacts.count_documents({})

    logger.info(
        "pipeline_stats_collected",
        total_artifacts=total_artifacts,
        total_pages=total_pages,
    )

    return PipelineStatsResponse(
        total_artifacts=total_artifacts,
        total_pages=total_pages,
        pages_with_text=pages_with_text,
        pages_with_summary=pages_with_summary,
        pages_with_compounds=pages_with_compounds,
        pages_with_tags=pages_with_tags,
    )


@router.get("/vectors", status_code=status.HTTP_200_OK)
async def get_vector_stats(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> VectorStatsResponse:
    """Get vector store and embedding model statistics (admin only)."""
    if not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    logger.info("vector_stats_requested")

    vector_store = container[VectorStore]
    compound_store = container[CompoundVectorStore]
    summary_store = container[SummaryVectorStore]
    generator = container[EmbeddingGenerator]
    chemberta = container[ChemBertaEmbeddingGenerator]

    page_info = await vector_store.get_collection_info()
    compound_info = await compound_store.get_compound_collection_info()
    summary_info = await summary_store.get_collection_info()

    collections = [
        CollectionStats(
            collection_name=info.get("collection_name", info.get("name", "unknown")),
            points_count=info.get("points_count", 0),
            indexed_vectors_count=info.get("indexed_vectors_count", 0),
            status=info.get("status", "unknown"),
        )
        for info in [page_info, compound_info, summary_info]
    ]

    embedding_model = await generator.get_model_info()
    chemberta_model = await chemberta.get_model_info()
    embedding_model_info = {
        "text": embedding_model,
        "smiles": chemberta_model,
    }

    reranker_info: dict | None = None
    try:
        reranker = container[Reranker]
        if reranker:
            reranker_info = {
                "model_name": getattr(reranker, "model_name", "unknown"),
                "device": getattr(reranker, "device", "unknown"),
            }
    except Exception:
        reranker_info = None

    logger.info("vector_stats_collected", collections=len(collections))

    return VectorStatsResponse(
        collections=collections,
        embedding_model=embedding_model_info,
        reranker=reranker_info,
    )


# ── Analytics Aggregation Endpoints ────────────────────────────────────────


def _period_to_days(period: str) -> int:
    return {"day": 1, "week": 7, "month": 30}.get(period, 7)


@router.get("/token-usage", status_code=status.HTTP_200_OK)
async def get_token_usage_stats(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    period: str = Query("week", pattern="^(day|week|month)$"),
) -> TokenUsageStatsResponse:
    """Aggregate token usage from chat messages (admin only)."""
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    analytics = container[AnalyticsReadModel]
    return await analytics.get_token_usage(_period_to_days(period), workspace_id=auth.workspace_id)


@router.get("/chat-latency", status_code=status.HTTP_200_OK)
async def get_chat_latency_stats(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    period: str = Query("week", pattern="^(day|week|month)$"),
) -> ChatLatencyStatsResponse:
    """Aggregate pipeline step latency from chat agent traces (admin only)."""
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    analytics = container[AnalyticsReadModel]
    return await analytics.get_chat_latency(_period_to_days(period), workspace_id=auth.workspace_id)


@router.get("/search-quality", status_code=status.HTTP_200_OK)
async def get_search_quality_stats(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    period: str = Query("week", pattern="^(day|week|month)$"),
) -> SearchQualityStatsResponse:
    """Aggregate search quality metrics from user activity (admin only)."""
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    analytics = container[AnalyticsReadModel]
    return await analytics.get_search_quality(
        _period_to_days(period),
        workspace_id=auth.workspace_id,
    )


@router.get("/grounding", status_code=status.HTTP_200_OK)
async def get_grounding_stats(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    period: str = Query("week", pattern="^(day|week|month)$"),
) -> GroundingStatsResponse:
    """Aggregate grounding score distribution from chat messages (admin only)."""
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    analytics = container[AnalyticsReadModel]
    return await analytics.get_grounding_stats(
        _period_to_days(period),
        workspace_id=auth.workspace_id,
    )


@router.get("/knowledge-gaps", status_code=status.HTTP_200_OK)
async def get_knowledge_gaps(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    period: str = Query("week", pattern="^(day|week|month)$"),
) -> KnowledgeGapsResponse:
    """Entities detected in chat queries that the corpus couldn't ground (admin only)."""
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    analytics = container[AnalyticsReadModel]
    return await analytics.get_knowledge_gaps(
        _period_to_days(period),
        workspace_id=auth.workspace_id,
    )


@router.get("/citation-frequency", status_code=status.HTTP_200_OK)
async def get_citation_frequency(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    period: str = Query("week", pattern="^(day|week|month)$"),
) -> CitationFrequencyResponse:
    """Document citation frequency from chat answers (admin only)."""
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    analytics = container[AnalyticsReadModel]
    return await analytics.get_citation_frequency(
        _period_to_days(period),
        workspace_id=auth.workspace_id,
    )
