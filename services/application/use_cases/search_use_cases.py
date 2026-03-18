"""Search use cases: summary search and hierarchical cross-collection search."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.dtos.search_dtos import (
    ChunkHit,
    HierarchicalSearchRequest,
    HierarchicalSearchResponse,
    SummaryHit,
    SummarySearchRequest,
    SummarySearchResponse,
    SummarySearchResultDTO,
)

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.embedding_generator import EmbeddingGenerator
    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.repositories.page_read_models import PageReadModel
    from application.ports.summary_vector_store import SummarySearchResult, SummaryVectorStore
    from application.ports.vector_store import PageSearchResult, VectorStore

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Shared enrichment helpers
# ---------------------------------------------------------------------------


async def _resolve_artifact_title(
    artifact_id: UUID,
    artifact_read_model: ArtifactReadModel,
    fallback_title: str | None = None,
) -> str | None:
    """Return the best-available title for an artifact.

    Uses the existing *fallback_title* when present, otherwise queries the
    read model.
    """
    if fallback_title:
        return fallback_title
    artifact = await artifact_read_model.get_artifact_by_id(artifact_id)
    if artifact:
        return artifact.title_mention.title if artifact.title_mention else artifact.source_filename
    return None


# ---------------------------------------------------------------------------
# Summary search
# ---------------------------------------------------------------------------


class SearchSummariesUseCase:
    """Search the unified summary_embeddings collection by semantic similarity.

    Returns page and/or artifact summary hits ordered by cosine similarity.
    """

    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        summary_vector_store: SummaryVectorStore,
        artifact_read_model: ArtifactReadModel,
    ) -> None:
        self.embedding_generator = embedding_generator
        self.summary_vector_store = summary_vector_store
        self.artifact_read_model = artifact_read_model

    async def execute(
        self,
        request: SummarySearchRequest,
        workspace_id: UUID | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> Result[SummarySearchResponse, AppError]:
        try:
            logger.info(
                "search_summaries_start",
                query_length=len(request.query_text),
                entity_type=request.entity_type,
                limit=request.limit,
            )

            query_embedding = await self.embedding_generator.generate_text_embedding(
                text=request.query_text,
            )

            hits = await self.summary_vector_store.search_summaries(
                query_embedding=query_embedding,
                limit=request.limit,
                entity_type_filter=request.entity_type,
                artifact_id_filter=request.artifact_id,
                score_threshold=request.score_threshold,
                allowed_artifact_ids=allowed_artifact_ids,
                workspace_id=workspace_id,
            )

            result_dtos: list[SummarySearchResultDTO] = []
            for h in hits:
                title = await _resolve_artifact_title(
                    h.artifact_id,
                    self.artifact_read_model,
                    h.artifact_title,
                )
                result_dtos.append(
                    SummarySearchResultDTO(
                        entity_type=h.entity_type,
                        entity_id=h.entity_id,
                        artifact_id=h.artifact_id,
                        similarity_score=h.score,
                        summary_text=h.summary_text,
                        artifact_title=title,
                        page_index=h.metadata.get("page_index"),
                        metadata=h.metadata,
                    ),
                )

            model_info = await self.embedding_generator.get_model_info()

            logger.info("search_summaries_success", results_count=len(result_dtos))

            return Success(
                SummarySearchResponse(
                    query=request.query_text,
                    results=result_dtos,
                    total_results=len(result_dtos),
                    model_used=str(model_info.get("model_name", "unknown")),
                ),
            )

        except Exception as e:
            logger.exception(
                "search_summaries_failed",
                query=request.query_text[:100],
                error=str(e),
            )
            return Failure(AppError("internal_error", f"Failed to search summaries: {e!s}"))


# ---------------------------------------------------------------------------
# Hierarchical (cross-collection) search
# ---------------------------------------------------------------------------


class HierarchicalSearchUseCase:
    """Cross-collection semantic search over raw chunks and summaries.

    Queries both page_embeddings (raw chunks) and summary_embeddings
    (page + artifact summaries) in parallel, then returns the results
    grouped by type for the caller to merge or present hierarchically.

    Phase 1 implementation: pure dense search, client-side merge.
    """

    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        vector_store: VectorStore,
        summary_vector_store: SummaryVectorStore,
        page_read_model: PageReadModel,
        artifact_read_model: ArtifactReadModel,
    ) -> None:
        self.embedding_generator = embedding_generator
        self.vector_store = vector_store
        self.summary_vector_store = summary_vector_store
        self.page_read_model = page_read_model
        self.artifact_read_model = artifact_read_model

    async def execute(
        self,
        request: HierarchicalSearchRequest,
        workspace_id: UUID | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> Result[HierarchicalSearchResponse, AppError]:
        try:
            logger.info(
                "hierarchical_search_start",
                query_length=len(request.query_text),
                limit=request.limit,
                include_chunks=request.include_chunks,
            )

            query_embedding = await self.embedding_generator.generate_text_embedding(
                text=request.query_text,
            )

            summary_hits = await self._search_summaries(
                query_embedding,
                request,
                allowed_artifact_ids,
                workspace_id,
            )

            chunk_hits: list[ChunkHit] = []
            if request.include_chunks:
                chunk_hits = await self._search_chunks(
                    query_embedding,
                    request,
                    allowed_artifact_ids,
                    workspace_id,
                )

            model_info = await self.embedding_generator.get_model_info()

            logger.info(
                "hierarchical_search_success",
                summary_hits=len(summary_hits),
                chunk_hits=len(chunk_hits),
            )

            return Success(
                HierarchicalSearchResponse(
                    query=request.query_text,
                    summary_hits=summary_hits,
                    chunk_hits=chunk_hits,
                    total_summary_hits=len(summary_hits),
                    total_chunk_hits=len(chunk_hits),
                    model_used=str(model_info.get("model_name", "unknown")),
                ),
            )

        except Exception as e:
            logger.exception(
                "hierarchical_search_failed",
                query=request.query_text[:100],
                error=str(e),
            )
            return Failure(
                AppError("internal_error", f"Failed to perform hierarchical search: {e!s}"),
            )

    async def _search_summaries(
        self,
        query_embedding: object,
        request: HierarchicalSearchRequest,
        allowed_artifact_ids: list[UUID] | None,
        workspace_id: UUID | None,
    ) -> list[SummaryHit]:
        """Query the summary collection and enrich with artifact titles."""
        summary_hits_raw: list[
            SummarySearchResult
        ] = await self.summary_vector_store.search_summaries(
            query_embedding=query_embedding,
            limit=request.limit,
            score_threshold=request.score_threshold,
            allowed_artifact_ids=allowed_artifact_ids,
            workspace_id=workspace_id,
        )
        result: list[SummaryHit] = []
        for h in summary_hits_raw:
            title = await _resolve_artifact_title(
                h.artifact_id,
                self.artifact_read_model,
                h.artifact_title,
            )
            result.append(
                SummaryHit(
                    entity_type=h.entity_type,
                    entity_id=h.entity_id,
                    artifact_id=h.artifact_id,
                    score=h.score,
                    summary_text=h.summary_text,
                    artifact_title=title,
                    page_index=h.metadata.get("page_index"),
                ),
            )
        return result

    async def _search_chunks(
        self,
        query_embedding: object,
        request: HierarchicalSearchRequest,
        allowed_artifact_ids: list[UUID] | None,
        workspace_id: UUID | None,
    ) -> list[ChunkHit]:
        """Query the raw chunk collection, deduplicate by page, enrich."""
        raw_results: list[PageSearchResult] = await self.vector_store.search_similar_pages(
            query_embedding=query_embedding,
            limit=request.limit * 3,
            score_threshold=request.score_threshold,
            allowed_artifact_ids=allowed_artifact_ids,
            workspace_id=workspace_id,
        )

        # Deduplicate: keep best chunk per page
        best_by_page: dict[UUID, tuple[float, int]] = {}
        for r in raw_results:
            existing_score, _ = best_by_page.get(r.page_id, (-1.0, 0))
            if r.score > existing_score:
                best_by_page[r.page_id] = (r.score, r.page_index)

        top_pages = sorted(best_by_page.items(), key=lambda x: x[1][0], reverse=True)[
            : request.limit
        ]

        chunk_hits: list[ChunkHit] = []
        for page_id, (score, page_index) in top_pages:
            artifact_id = next(r.artifact_id for r in raw_results if r.page_id == page_id)
            chunk_hits.append(await self._enrich_chunk_hit(page_id, artifact_id, page_index, score))
        return chunk_hits

    async def _enrich_chunk_hit(
        self,
        page_id: UUID,
        artifact_id: UUID,
        page_index: int,
        score: float,
    ) -> ChunkHit:
        """Build a single ChunkHit enriched with read-model data."""
        text_preview = None
        page_name = None
        page = await self.page_read_model.get_page_by_id(page_id)
        if page:
            page_name = page.name
            if page.text_mention and page.text_mention.text:
                text_preview = page.text_mention.text[:500]

        artifact_name = await _resolve_artifact_title(artifact_id, self.artifact_read_model)

        return ChunkHit(
            page_id=page_id,
            artifact_id=artifact_id,
            page_index=page_index,
            score=score,
            text_preview=text_preview,
            artifact_name=artifact_name,
            page_name=page_name,
        )
