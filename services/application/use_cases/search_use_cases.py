"""Search use cases: summary search and hierarchical cross-collection search."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.embedding_dtos import RerankInfoDTO
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
from application.ports.reranker import RerankDocument
from application.use_cases.embedding_use_cases import build_chunk_context

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.embedding_generator import EmbeddingGenerator
    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.repositories.page_read_models import PageReadModel
    from application.ports.reranker import Reranker
    from application.ports.sparse_embedding_generator import SparseEmbeddingGenerator
    from application.ports.summary_vector_store import SummarySearchResult, SummaryVectorStore
    from application.ports.vector_store import VectorStore

logger = structlog.get_logger()

# Enough page text for a search card's clamped snippet. Callers that feed the
# text to a model ask for more; see HierarchicalSearchUseCase.execute.
_DEFAULT_PREVIEW_CHARS = 500

# Cap on the passage handed to the cross-encoder. Its own limit is 512 tokens,
# so this only bounds the slice we build; the model truncates whatever is left.
_RERANK_CHARS = 2000

# Candidates fetched per requested result, so the reranker has something to
# choose from. Not conditioned on whether a reranker is configured: retrieval
# width is a property of retrieval, and tying it to a downstream stage made
# RERANKER_ENABLED=false quietly a two-variable change -- no reranking *and* a
# third of the candidates -- which is not the ablation it reads as.
_RERANK_POOL_MULTIPLIER = 3


def rerank_passage(meta: dict, page_text: str, artifact_title: str | None = None) -> str:
    """The passage a reranker should score for one hit.

    Prefers the chunk that actually matched (``chunk_text``, written into the
    payload at index time). Points written before that field existed fall back to
    a window of page text centred on the matched chunk, located from
    ``chunk_index``/``chunk_count`` — both unconditional payload fields. The page
    *prefix* is the wrong passage on any page whose content sits below the fold:
    the reranker then scores a slide on its title block and demotes it, which is
    how a slide that dense retrieval ranked in its top 10 falls out of the list.

    The heading breadcrumb is prepended because a chunk taken out of the page
    loses the slide title that a bare table needs to be judged against.

    ``artifact_title`` restores the rest of what the chunk carried at index time.
    Embedding prepends :func:`build_chunk_context` to every chunk before it is
    vectorised, so the retriever matches on document identity; the reranker was
    handed the body alone and could not tell one deck's IC50 table from another
    deck's. Measured on the H8 set-algebra questions with production
    sub-queries: 87.8% -> 97.6% gold recall, 4 -> 9 of 10 questions fully
    answered. None is accepted so a caller that cannot resolve a title still
    gets exactly the old passage.
    """
    body = meta.get("chunk_text") or ""
    if not body and page_text:
        ci, cc = meta.get("chunk_index"), meta.get("chunk_count")
        start = (
            max(0, int(len(page_text) * ci / cc) - _RERANK_CHARS // 4)
            if ci is not None and cc
            else 0
        )
        body = page_text[start : start + _RERANK_CHARS]
    heading = " > ".join(meta.get("section_path") or [])
    passage = f"{heading}\n{body}" if heading and body else body
    passage = passage.strip()
    if artifact_title and passage:
        # page_summary is omitted on purpose -- see build_chunk_context.
        passage = (
            build_chunk_context(
                artifact_title, meta.get("page_index") or 0, meta.get("tags"), None
            )
            + passage
        )
    return passage[:_RERANK_CHARS]


# ---------------------------------------------------------------------------
# Shared enrichment helpers
# ---------------------------------------------------------------------------


class ArtifactInfo:
    """Resolved artifact metadata for enriching search results."""

    __slots__ = ("authors", "presentation_date", "title")

    def __init__(
        self,
        title: str | None = None,
        authors: list[str] | None = None,
        presentation_date: str | None = None,
    ) -> None:
        self.title = title
        self.authors = authors or []
        self.presentation_date = presentation_date


def _date_to_str(val: object) -> str | None:
    """Convert a datetime or string date to ISO string."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if hasattr(val, "isoformat"):
        return val.isoformat()  # type: ignore[union-attr]
    return str(val)


async def resolve_artifact_info(
    artifact_id: UUID,
    artifact_read_model: ArtifactReadModel,
    fallback_title: str | None = None,
    workspace_id: UUID | None = None,
) -> ArtifactInfo:
    """Return title, authors, and date for an artifact."""
    artifact = await artifact_read_model.get_artifact_by_id(artifact_id, workspace_id=workspace_id)
    if artifact:
        return ArtifactInfo(
            title=artifact.title_mention.title
            if artifact.title_mention
            else (fallback_title or artifact.source_filename),
            authors=[am.name for am in artifact.author_mentions]
            if artifact.author_mentions
            else [],
            presentation_date=_date_to_str(artifact.presentation_date.date)
            if artifact.presentation_date
            else None,
        )
    return ArtifactInfo()


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
                tags=request.tags,
                entity_types=request.entity_types_filter,
                tag_match_mode=request.tag_match_mode,
            )

            result_dtos: list[SummarySearchResultDTO] = []
            for h in hits:
                info = await resolve_artifact_info(
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
                        artifact_title=info.title,
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
        reranker: Reranker | None = None,
        sparse_embedding_generator: SparseEmbeddingGenerator | None = None,
    ) -> None:
        self.embedding_generator = embedding_generator
        self.vector_store = vector_store
        self.summary_vector_store = summary_vector_store
        self.page_read_model = page_read_model
        self.artifact_read_model = artifact_read_model
        self.reranker = reranker
        self.sparse_embedding_generator = sparse_embedding_generator

    async def execute(
        self,
        request: HierarchicalSearchRequest,
        workspace_id: UUID | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
        text_preview_chars: int = _DEFAULT_PREVIEW_CHARS,
        keep_full_rerank_pool: bool = False,
    ) -> Result[HierarchicalSearchResponse, AppError]:
        """Search summaries and chunks, merged and reranked.

        ``text_preview_chars`` is how much page text a chunk hit carries back. It
        is an argument rather than a constant because the two consumers need
        different amounts and neither should silently impose its answer on the
        other: the search UI renders a clamped snippet, while chat feeds the text
        to a model that must read it. It is deliberately not a field on the
        request DTO, which is an HTTP body -- this is an internal concern.

        ``keep_full_rerank_pool`` splits the same way. Chunk retrieval fetches
        ``limit * 3`` candidates so the reranker has something to choose from,
        then discards the losers. That is right for the search UI, where
        ``limit`` is a promise about the response length. It is wrong for the
        agentic loop, which issues several sub-queries and merges them in
        RetrievalAccumulator keeping the best score per page: a page that ranks
        11th on one sub-query and 1st on the next can only win that merge if it
        survived the first search. Discarding it costs the answer, and the
        candidate was already retrieved, reranked and paid for. Assembly, not
        retrieval, does the real limiting downstream.
        """
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
            chunk_rerank_info: RerankInfoDTO | None = None
            if request.include_chunks:
                chunk_hits, chunk_rerank_info = await self._search_chunks(
                    query_embedding,
                    request,
                    allowed_artifact_ids,
                    workspace_id,
                    text_preview_chars,
                    keep_full_rerank_pool,
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
                    chunk_rerank_info=chunk_rerank_info,
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
            tags=request.tags,
            entity_types=request.entity_types_filter,
            tag_match_mode=request.tag_match_mode,
        )
        result: list[SummaryHit] = []
        for h in summary_hits_raw:
            info = await resolve_artifact_info(
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
                    artifact_title=info.title,
                    page_index=h.metadata.get("page_index"),
                    authors=info.authors,
                    presentation_date=info.presentation_date,
                ),
            )
        return result

    async def _search_chunks(
        self,
        query_embedding: object,
        request: HierarchicalSearchRequest,
        allowed_artifact_ids: list[UUID] | None,
        workspace_id: UUID | None,
        text_preview_chars: int = _DEFAULT_PREVIEW_CHARS,
        keep_full_rerank_pool: bool = False,
    ) -> tuple[list[ChunkHit], RerankInfoDTO | None]:
        """Query the raw chunk collection with server-side dedup, rerank, then enrich."""
        retrieval_limit = request.limit * _RERANK_POOL_MULTIPLIER

        filter_kwargs = {
            "limit": retrieval_limit,
            "score_threshold": request.score_threshold,
            "allowed_artifact_ids": allowed_artifact_ids,
            "workspace_id": workspace_id,
            "tags": request.tags,
            "entity_types": request.entity_types_filter,
            "tag_match_mode": request.tag_match_mode,
        }

        if self.sparse_embedding_generator:
            sparse_query = self.sparse_embedding_generator.generate_sparse_embedding(
                request.query_text,
            )
            grouped_results = await self.vector_store.search_hybrid_grouped(
                dense_query=query_embedding,
                sparse_query=sparse_query,
                **filter_kwargs,
            )
        else:
            grouped_results = await self.vector_store.search_pages_grouped(
                query_embedding=query_embedding,
                **filter_kwargs,
            )

        rerank_info: RerankInfoDTO | None = None
        rerank_scores: dict[str, tuple[float | None, int | None]] = {}

        if self.reranker and grouped_results:
            # One read per distinct *artifact*, not per candidate: a search
            # returns limit*3 hits but they cluster into far fewer documents.
            # _enrich_chunk_hit below already pays a per-hit read, so this is
            # strictly the cheaper of the two lookups in this method.
            titles: dict[str, str] = {}
            for aid in {r.artifact_id for r in grouped_results}:
                info = await resolve_artifact_info(
                    aid, self.artifact_read_model, workspace_id=workspace_id
                )
                if info.title:
                    titles[str(aid)] = info.title

            rerank_docs: list[RerankDocument] = []
            for r in grouped_results:
                meta = r.metadata or {}
                page_text = ""
                if not meta.get("chunk_text"):
                    # Only points written before chunk_text existed still need
                    # the page read — this loop used to run one Mongo fetch per
                    # candidate, and there are limit*3 of them per search.
                    page = await self.page_read_model.get_page_by_id(r.page_id)
                    if page and page.text_mention and page.text_mention.text:
                        page_text = page.text_mention.text
                text = rerank_passage(meta, page_text, titles.get(str(r.artifact_id)))
                if not text:
                    continue
                rerank_docs.append(RerankDocument(id=str(r.page_id), text=text))

            reranked = self.reranker.rerank(
                query=request.query_text,
                documents=rerank_docs,
                # None keeps every candidate that was retrieved and scored.
                # See ``keep_full_rerank_pool`` in execute() for why the
                # agentic caller must not have its pool cut here.
                top_k=None if keep_full_rerank_pool else request.limit,
            )

            rerank_scores = {r.id: (r.score, r.original_rank) for r in reranked}
            rerank_order = {r.id: i for i, r in enumerate(reranked)}
            grouped_results = sorted(
                [r for r in grouped_results if str(r.page_id) in rerank_order],
                key=lambda r: rerank_order[str(r.page_id)],
            )

            promotions = [r.original_rank - i for i, r in enumerate(reranked)]
            rerank_info = RerankInfoDTO(
                reranker_model=self.reranker.model_name
                if hasattr(self.reranker, "model_name")
                else "unknown",
                candidates_before=len(rerank_docs),
                results_after=len(reranked),
                top_promotion=max(promotions) if promotions else None,
            )

            logger.info(
                "hierarchical_chunk_rerank",
                candidates=len(rerank_docs),
                returned=len(reranked),
                top_promotion=rerank_info.top_promotion,
            )
        elif not keep_full_rerank_pool:
            # The pool is widened for the reranker's benefit unconditionally, so
            # when there is no reranker to spend it, the cut that top_k would
            # have made has to happen here -- otherwise ``limit`` stops bounding
            # the response the moment reranking is switched off.
            grouped_results = grouped_results[: request.limit]

        chunk_hits: list[ChunkHit] = []
        for r in grouped_results:
            rr_score, rr_original = rerank_scores.get(str(r.page_id), (None, None))
            hit = await self._enrich_chunk_hit(
                r.page_id,
                r.artifact_id,
                r.page_index,
                r.score,
                text_preview_chars,
            )
            hit.rerank_score = rr_score
            hit.original_rank = rr_original
            chunk_hits.append(hit)
        return chunk_hits, rerank_info

    async def _enrich_chunk_hit(
        self,
        page_id: UUID,
        artifact_id: UUID,
        page_index: int,
        score: float,
        text_preview_chars: int = _DEFAULT_PREVIEW_CHARS,
    ) -> ChunkHit:
        """Build a single ChunkHit enriched with read-model data."""
        text_preview = None
        page_name = None
        page = await self.page_read_model.get_page_by_id(page_id)
        if page:
            page_name = page.name
            if page.text_mention and page.text_mention.text:
                text_preview = page.text_mention.text[:text_preview_chars]

        info = await resolve_artifact_info(artifact_id, self.artifact_read_model)

        return ChunkHit(
            page_id=page_id,
            artifact_id=artifact_id,
            page_index=page_index,
            score=score,
            text_preview=text_preview,
            artifact_name=info.title,
            page_name=page_name,
        )
