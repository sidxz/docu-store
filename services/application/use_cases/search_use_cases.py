"""Search use cases: summary search and hierarchical cross-collection search."""

from uuid import UUID

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
from application.ports.embedding_generator import EmbeddingGenerator
from application.ports.repositories.page_read_models import PageReadModel
from application.ports.summary_vector_store import SummaryVectorStore
from application.ports.vector_store import VectorStore

logger = structlog.get_logger()


class SearchSummariesUseCase:
    """Search the unified summary_embeddings collection by semantic similarity.

    Returns page and/or artifact summary hits ordered by cosine similarity.
    """

    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        summary_vector_store: SummaryVectorStore,
    ) -> None:
        self.embedding_generator = embedding_generator
        self.summary_vector_store = summary_vector_store

    async def execute(
        self, request: SummarySearchRequest
    ) -> Result[SummarySearchResponse, AppError]:
        try:
            logger.info(
                "search_summaries_start",
                query_length=len(request.query_text),
                entity_type=request.entity_type,
                limit=request.limit,
            )

            query_embedding = await self.embedding_generator.generate_text_embedding(
                text=request.query_text
            )

            hits = await self.summary_vector_store.search_summaries(
                query_embedding=query_embedding,
                limit=request.limit,
                entity_type_filter=request.entity_type,
                artifact_id_filter=request.artifact_id,
                score_threshold=request.score_threshold,
            )

            result_dtos = [
                SummarySearchResultDTO(
                    entity_type=h.entity_type,
                    entity_id=h.entity_id,
                    artifact_id=h.artifact_id,
                    similarity_score=h.score,
                    summary_text=h.summary_text,
                    artifact_title=h.artifact_title,
                    metadata=h.metadata,
                )
                for h in hits
            ]

            model_info = await self.embedding_generator.get_model_info()

            logger.info(
                "search_summaries_success",
                results_count=len(result_dtos),
            )

            return Success(
                SummarySearchResponse(
                    query=request.query_text,
                    results=result_dtos,
                    total_results=len(result_dtos),
                    model_used=str(model_info.get("model_name", "unknown")),
                )
            )

        except Exception as e:
            logger.exception(
                "search_summaries_failed",
                query=request.query_text[:100],
                error=str(e),
            )
            return Failure(AppError("internal_error", f"Failed to search summaries: {e!s}"))


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
    ) -> None:
        self.embedding_generator = embedding_generator
        self.vector_store = vector_store
        self.summary_vector_store = summary_vector_store
        self.page_read_model = page_read_model

    async def execute(
        self, request: HierarchicalSearchRequest
    ) -> Result[HierarchicalSearchResponse, AppError]:
        try:
            logger.info(
                "hierarchical_search_start",
                query_length=len(request.query_text),
                limit=request.limit,
                include_chunks=request.include_chunks,
            )

            # Single embedding — reused for both collections
            query_embedding = await self.embedding_generator.generate_text_embedding(
                text=request.query_text
            )

            # Query summary collection (always)
            summary_hits_raw = await self.summary_vector_store.search_summaries(
                query_embedding=query_embedding,
                limit=request.limit,
                score_threshold=request.score_threshold,
            )
            summary_hits = [
                SummaryHit(
                    entity_type=h.entity_type,
                    entity_id=h.entity_id,
                    artifact_id=h.artifact_id,
                    score=h.score,
                    summary_text=h.summary_text,
                    artifact_title=h.artifact_title,
                )
                for h in summary_hits_raw
            ]

            # Query raw chunk collection (optional)
            chunk_hits: list[ChunkHit] = []
            if request.include_chunks:
                # Over-fetch to allow dedup by page
                raw_results = await self.vector_store.search_similar_pages(
                    query_embedding=query_embedding,
                    limit=request.limit * 3,
                    score_threshold=request.score_threshold,
                )

                # Deduplicate: keep best chunk per page
                best_by_page: dict[UUID, tuple[float, int]] = {}
                for r in raw_results:
                    existing_score, _ = best_by_page.get(r.page_id, (-1.0, 0))
                    if r.score > existing_score:
                        best_by_page[r.page_id] = (r.score, r.page_index)

                # Build chunk hits, enriched with text preview from read model
                top_pages = sorted(best_by_page.items(), key=lambda x: x[1][0], reverse=True)[
                    : request.limit
                ]
                for page_id, (score, page_index) in top_pages:
                    # Find artifact_id from raw results
                    artifact_id = next(
                        r.artifact_id for r in raw_results if r.page_id == page_id
                    )
                    text_preview = None
                    page = await self.page_read_model.get_page_by_id(page_id)
                    if page and page.text_mention and page.text_mention.text:
                        text_preview = page.text_mention.text[:500]

                    chunk_hits.append(
                        ChunkHit(
                            page_id=page_id,
                            artifact_id=artifact_id,
                            page_index=page_index,
                            score=score,
                            text_preview=text_preview,
                        )
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
                )
            )

        except Exception as e:
            logger.exception(
                "hierarchical_search_failed",
                query=request.query_text[:100],
                error=str(e),
            )
            return Failure(
                AppError("internal_error", f"Failed to perform hierarchical search: {e!s}")
            )
