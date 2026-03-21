"""Step 2: Retrieve relevant sources using existing search use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Failure

from application.dtos.chat_dtos import SourceCitationDTO
from application.dtos.search_dtos import HierarchicalSearchRequest, SummarySearchRequest
from infrastructure.chat.models import QuestionAnalysis
from infrastructure.config import settings

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.repositories.page_read_models import PageReadModel
    from application.use_cases.search_use_cases import (
        HierarchicalSearchUseCase,
        SearchSummariesUseCase,
    )

log = structlog.get_logger(__name__)


class RetrievalNode:
    """Execute search against existing collections based on the analysis strategy."""

    def __init__(
        self,
        hierarchical_search: HierarchicalSearchUseCase,
        summary_search: SearchSummariesUseCase,
        page_read_model: PageReadModel,
        max_results: int = 10,
    ) -> None:
        self._hierarchical_search = hierarchical_search
        self._summary_search = summary_search
        self._page_read_model = page_read_model
        self._max_results = max_results

    async def run(
        self,
        analysis: QuestionAnalysis,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> tuple[list[SourceCitationDTO], str]:
        """Retrieve sources and build a formatted sources string for the LLM.

        Returns:
            Tuple of (citations list, formatted sources text for prompt).
        """
        strategy = analysis.search_strategy
        query = analysis.reformulated_query

        log.info("chat.retrieval.start", strategy=strategy, query_len=len(query))

        if settings.chat_debug:
            log.info(
                "chat.debug.retrieval.input",
                query=query,
                strategy=strategy,
                entities=analysis.entities,
                max_results=self._max_results,
                workspace_id=str(workspace_id),
            )

        if strategy == "summary":
            return await self._search_summaries(query, workspace_id, allowed_artifact_ids)

        # Default: hierarchical (best for most queries)
        return await self._search_hierarchical(query, workspace_id, allowed_artifact_ids)

    async def _search_hierarchical(
        self,
        query: str,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> tuple[list[SourceCitationDTO], str]:
        request = HierarchicalSearchRequest(
            query_text=query,
            limit=self._max_results,
            include_chunks=True,
        )
        result = await self._hierarchical_search.execute(
            request,
            workspace_id=workspace_id,
            allowed_artifact_ids=allowed_artifact_ids,
        )

        if isinstance(result, Failure):
            log.warning("chat.retrieval.hierarchical_failed", error=str(result.failure()))
            return [], "No sources found."

        response = result.unwrap()
        citations: list[SourceCitationDTO] = []
        source_texts: list[str] = []
        idx = 1

        # Build artifact metadata lookup from summary hits (authors, dates)
        artifact_meta: dict[str, tuple[list[str], str | None]] = {}
        for sh in response.summary_hits:
            aid = str(sh.artifact_id)
            if aid not in artifact_meta:
                artifact_meta[aid] = (sh.authors or [], sh.presentation_date)

        # Chunk hits provide the most granular evidence
        for hit in response.chunk_hits:
            full_text = await self._get_page_text(hit.page_id)
            excerpt = full_text[:1500] if full_text else (hit.text_preview or "")
            authors, pdate = artifact_meta.get(str(hit.artifact_id), ([], None))
            citations.append(
                SourceCitationDTO(
                    artifact_id=hit.artifact_id,
                    artifact_title=hit.artifact_name,
                    authors=authors,
                    presentation_date=pdate,
                    page_id=hit.page_id,
                    page_index=hit.page_index,
                    page_name=hit.page_name,
                    text_excerpt=excerpt[:500],
                    similarity_score=hit.rerank_score or hit.score,
                    citation_index=idx,
                ),
            )
            source_texts.append(
                f"[{idx}] (Document: {hit.artifact_name or 'Unknown'}, "
                f"Page {hit.page_index})\n{excerpt}",
            )
            idx += 1

        # Summary hits for broader context
        for hit in response.summary_hits[:3]:
            citations.append(
                SourceCitationDTO(
                    artifact_id=hit.artifact_id,
                    artifact_title=hit.artifact_title,
                    authors=hit.authors or [],
                    presentation_date=hit.presentation_date,
                    page_id=hit.entity_id if hit.entity_type == "page" else None,
                    page_index=hit.page_index,
                    text_excerpt=hit.summary_text[:500] if hit.summary_text else None,
                    similarity_score=hit.score,
                    citation_index=idx,
                ),
            )
            source_texts.append(
                f"[{idx}] (Summary - {hit.entity_type}: {hit.artifact_title or 'Unknown'})\n"
                f"{hit.summary_text or ''}",
            )
            idx += 1

        formatted = "\n\n".join(source_texts) if source_texts else "No relevant sources found."
        log.info(
            "chat.retrieval.done",
            total_citations=len(citations),
            chunk_hits=len(response.chunk_hits),
            summary_hits=len(response.summary_hits),
        )

        if settings.chat_debug:
            for c in citations:
                log.info(
                    "chat.debug.retrieval.citation",
                    idx=c.citation_index,
                    artifact=c.artifact_title,
                    page_index=c.page_index,
                    score=c.similarity_score,
                    excerpt_len=len(c.text_excerpt) if c.text_excerpt else 0,
                )
            log.info(
                "chat.debug.retrieval.formatted_sources",
                total_chars=len(formatted),
                preview=formatted[:500],
            )

        return citations, formatted

    async def _search_summaries(
        self,
        query: str,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> tuple[list[SourceCitationDTO], str]:
        request = SummarySearchRequest(
            query_text=query,
            limit=self._max_results,
        )
        result = await self._summary_search.execute(
            request,
            workspace_id=workspace_id,
            allowed_artifact_ids=allowed_artifact_ids,
        )

        if isinstance(result, Failure):
            log.warning("chat.retrieval.summary_failed", error=str(result.failure()))
            return [], "No sources found."

        response = result.unwrap()
        citations: list[SourceCitationDTO] = []
        source_texts: list[str] = []

        for idx, hit in enumerate(response.results, 1):
            citations.append(
                SourceCitationDTO(
                    artifact_id=hit.artifact_id,
                    artifact_title=hit.artifact_title,
                    page_id=hit.entity_id if hit.entity_type == "page" else None,
                    page_index=hit.page_index,
                    text_excerpt=hit.summary_text[:500] if hit.summary_text else None,
                    similarity_score=hit.similarity_score,
                    citation_index=idx,
                ),
            )
            source_texts.append(
                f"[{idx}] ({hit.entity_type}: {hit.artifact_title or 'Unknown'})\n"
                f"{hit.summary_text or ''}",
            )

        formatted = "\n\n".join(source_texts) if source_texts else "No relevant sources found."
        log.info("chat.retrieval.done", total_citations=len(citations))
        return citations, formatted

    async def _get_page_text(self, page_id: UUID) -> str | None:
        """Fetch full page text from the read model."""
        page = await self._page_read_model.get_page_by_id(page_id)
        if page and page.text_mention and page.text_mention.text:
            return page.text_mention.text
        return None
