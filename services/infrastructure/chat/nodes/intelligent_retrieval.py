"""Stage 2 (Thinking Mode): Multi-path intelligent retrieval.

Multi-query parallel search with NER-driven metadata filters,
adaptive depth, chunk context expansion, and cross-query dedup.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from returns.result import Failure

from application.dtos.search_dtos import HierarchicalSearchRequest
from infrastructure.chat.models import QueryPlan, RetrievalResult
from infrastructure.config import settings

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.repositories.page_read_models import PageReadModel
    from application.ports.text_chunker import TextChunker
    from application.use_cases.search_use_cases import HierarchicalSearchUseCase

log = structlog.get_logger(__name__)


class IntelligentRetrievalNode:
    """Execute multi-path retrieval with metadata filters and context expansion."""

    def __init__(
        self,
        hierarchical_search: HierarchicalSearchUseCase,
        page_read_model: PageReadModel,
        text_chunker: TextChunker,
    ) -> None:
        self._hierarchical_search = hierarchical_search
        self._page_read_model = page_read_model
        self._chunker = text_chunker

    async def run(
        self,
        plan: QueryPlan,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> list[RetrievalResult]:
        _debug = settings.chat_debug
        limit = self._compute_limit(plan.confidence)

        # Build all queries: primary + sub_queries + hyde
        queries: list[tuple[str, str]] = [
            (plan.reformulated_query, "primary"),
        ]
        for i, sq in enumerate(plan.sub_queries):
            queries.append((sq, f"sub_query_{i}"))
        if plan.hyde_hypothesis:
            queries.append((plan.hyde_hypothesis, "hyde"))

        # Build filter params from NER entities + author mentions
        entity_type_filters = [ef.entity_type for ef in plan.ner_entity_filters] or None
        tag_filters = [ef.entity_text for ef in plan.ner_entity_filters]
        tag_filters += plan.author_mentions
        tag_filters = tag_filters or None

        if _debug:
            log.info(
                "chat.debug.intelligent_retrieval.start",
                query_count=len(queries),
                limit=limit,
                entity_type_filters=entity_type_filters,
                tag_filters=tag_filters,
            )

        # Run all queries in parallel — first with filters, fallback without
        tasks = [
            self._search_single(
                query_text=q,
                query_source=source,
                workspace_id=workspace_id,
                allowed_artifact_ids=allowed_artifact_ids,
                limit=limit,
                entity_types_filter=entity_type_filters,
                tags=tag_filters,
            )
            for q, source in queries
        ]
        results_per_query = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and handle errors
        all_results: list[RetrievalResult] = []
        for i, res in enumerate(results_per_query):
            if isinstance(res, BaseException):
                log.warning(
                    "chat.intelligent_retrieval.query_failed",
                    query_source=queries[i][1],
                    error=str(res),
                )
                continue
            all_results.extend(res)

        # Deduplicate by (page_id, chunk_index) for chunks, (entity_type, entity_id) for summaries
        deduped = self._deduplicate(all_results)

        # Sort by best score (rerank > similarity)
        deduped.sort(
            key=lambda r: r.rerank_score if r.rerank_score is not None else r.similarity_score,
            reverse=True,
        )

        log.info(
            "chat.intelligent_retrieval.done",
            total_raw=len(all_results),
            deduped=len(deduped),
            queries=len(queries),
        )

        return deduped

    async def _search_single(
        self,
        query_text: str,
        query_source: str,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
        limit: int,
        entity_types_filter: list[str] | None,
        tags: list[str] | None,
    ) -> list[RetrievalResult]:
        """Run a single HierarchicalSearch with optional filters + fallback."""
        # Try with filters first
        results = await self._execute_search(
            query_text, query_source, workspace_id, allowed_artifact_ids,
            limit, entity_types_filter, tags,
        )

        # Fallback: if filtered search returns < 3 results, re-run without filters
        if len(results) < 3 and (entity_types_filter or tags):
            log.info(
                "chat.intelligent_retrieval.filter_fallback",
                query_source=query_source,
                filtered_count=len(results),
            )
            unfiltered = await self._execute_search(
                query_text, query_source, workspace_id, allowed_artifact_ids,
                limit, None, None,
            )
            # Merge: keep filtered results (they're higher precision), add unfiltered
            seen = {self._dedup_key(r) for r in results}
            for r in unfiltered:
                if self._dedup_key(r) not in seen:
                    results.append(r)
                    seen.add(self._dedup_key(r))

        return results

    async def _execute_search(
        self,
        query_text: str,
        query_source: str,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
        limit: int,
        entity_types_filter: list[str] | None,
        tags: list[str] | None,
    ) -> list[RetrievalResult]:
        """Execute HierarchicalSearchUseCase and convert to RetrievalResult list."""
        request = HierarchicalSearchRequest(
            query_text=query_text,
            limit=limit,
            include_chunks=True,
            entity_types_filter=entity_types_filter,
            tags=tags,
            tag_match_mode="any",
        )

        result = await self._hierarchical_search.execute(
            request,
            workspace_id=workspace_id,
            allowed_artifact_ids=allowed_artifact_ids,
        )

        if isinstance(result, Failure):
            log.warning("chat.intelligent_retrieval.search_failed", error=str(result.failure()))
            return []

        response = result.unwrap()
        retrieval_results: list[RetrievalResult] = []

        # Build artifact metadata lookup from summary hits
        artifact_meta: dict[str, tuple[list[str], str | None]] = {}
        for sh in response.summary_hits:
            aid = str(sh.artifact_id)
            if aid not in artifact_meta:
                artifact_meta[aid] = (sh.authors or [], sh.presentation_date)

        # Process chunk hits with context expansion
        for hit in response.chunk_hits:
            expanded_text, matched_text = await self._expand_chunk_context(
                hit.page_id, hit.text_preview,
            )
            authors, pdate = artifact_meta.get(str(hit.artifact_id), ([], None))

            retrieval_results.append(
                RetrievalResult(
                    source_type="chunk",
                    artifact_id=hit.artifact_id,
                    artifact_title=hit.artifact_name,
                    authors=authors,
                    presentation_date=pdate,
                    page_id=hit.page_id,
                    page_index=hit.page_index,
                    page_name=hit.page_name,
                    expanded_text=expanded_text,
                    matched_text=matched_text,
                    similarity_score=hit.score,
                    rerank_score=hit.rerank_score,
                    query_source=query_source,
                ),
            )

        # Process summary hits
        for sh in response.summary_hits[:3]:
            summary_text = sh.summary_text or ""
            retrieval_results.append(
                RetrievalResult(
                    source_type="summary",
                    artifact_id=sh.artifact_id,
                    artifact_title=sh.artifact_title,
                    authors=sh.authors or [],
                    presentation_date=sh.presentation_date,
                    page_id=sh.entity_id if sh.entity_type == "page" else None,
                    page_index=sh.page_index,
                    expanded_text=summary_text,
                    matched_text=summary_text[:500],
                    similarity_score=sh.score,
                    query_source=query_source,
                ),
            )

        return retrieval_results

    async def _expand_chunk_context(
        self,
        page_id: UUID,
        text_preview: str | None,
    ) -> tuple[str, str]:
        """Fetch page text, re-chunk, and expand to include neighbor chunks.

        Returns (expanded_text, matched_text).
        """
        page = await self._page_read_model.get_page_by_id(page_id)
        if not page or not page.text_mention or not page.text_mention.text:
            fallback = text_preview or ""
            return fallback, fallback

        full_text = page.text_mention.text
        matched = text_preview or ""

        # Re-chunk using the same chunker params
        try:
            chunks = self._chunker.chunk_text(full_text)
        except ValueError:
            return full_text[:1500], matched

        # Find the chunk that best matches text_preview
        best_idx = 0
        if matched:
            best_overlap = 0
            for i, chunk in enumerate(chunks):
                # Simple overlap: count shared chars
                overlap = len(set(matched[:200]) & set(chunk.text[:200]))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_idx = i

        # Expand: chunk-1, chunk, chunk+1
        start_idx = max(0, best_idx - 1)
        end_idx = min(len(chunks), best_idx + 2)
        expanded_parts = [chunks[i].text for i in range(start_idx, end_idx)]
        expanded = "\n".join(expanded_parts)

        return expanded, chunks[best_idx].text if best_idx < len(chunks) else matched

    def _compute_limit(self, confidence: float) -> int:
        """Adaptive retrieval depth based on query confidence."""
        if confidence >= 0.8:
            return settings.chat_max_retrieval_results  # Standard (10)
        if confidence >= 0.5:
            return settings.chat_thinking_max_retrieval_results  # Deeper (15)
        return 20  # Maximum breadth

    def _dedup_key(self, r: RetrievalResult) -> str:
        if r.source_type == "chunk" and r.page_id:
            return f"chunk:{r.page_id}"
        if r.source_type == "summary":
            return f"summary:{r.artifact_id}:{r.page_id or 'artifact'}"
        return f"{r.source_type}:{r.artifact_id}:{r.page_id}"

    def _deduplicate(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """Deduplicate, keeping highest-scoring entry per key."""
        best: dict[str, RetrievalResult] = {}
        for r in results:
            key = self._dedup_key(r)
            score = r.rerank_score if r.rerank_score is not None else r.similarity_score
            if key not in best:
                best[key] = r
            else:
                existing_score = (
                    best[key].rerank_score
                    if best[key].rerank_score is not None
                    else best[key].similarity_score
                )
                if score > existing_score:
                    best[key] = r
        return list(best.values())
