"""Retrieval tools for the agentic retrieval loop.

Each tool wraps an existing search use case and returns results as
RetrievalResult models + a compact text summary for the LLM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from returns.result import Failure

from application.dtos.search_dtos import HierarchicalSearchRequest, SummarySearchRequest
from application.ports.tool_calling_llm import ToolDefinition
from infrastructure.chat.models import RetrievalResult

if TYPE_CHECKING:
    from application.ports.repositories.page_read_models import PageReadModel
    from application.use_cases.search_use_cases import (
        HierarchicalSearchUseCase,
        SearchSummariesUseCase,
    )

log = structlog.get_logger(__name__)


# ── Tool Definitions ──


SEARCH_DOCUMENTS_DEF = ToolDefinition(
    name="search_documents",
    description=(
        "Search the document store for relevant text chunks and summaries. "
        "Use this for finding specific information, data, or passages. "
        "Supports filtering by entity types (target, gene_name, compound_name) and tags."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query — be specific and use domain terms.",
            },
            "entity_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional NER entity type filters: target, gene_name, compound_name.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tag filters (entity names, author names).",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 10).",
            },
        },
        "required": ["query"],
    },
)

SEARCH_SUMMARIES_DEF = ToolDefinition(
    name="search_summaries",
    description=(
        "Search document and page summaries for broader context. "
        "Use this to understand what documents exist on a topic, "
        "or to find high-level overviews before drilling into specifics."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query for summaries.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 5).",
            },
        },
        "required": ["query"],
    },
)

GET_PAGE_CONTENT_DEF = ToolDefinition(
    name="get_page_content",
    description=(
        "Get the full text content of a specific page by its ID. "
        "Use this when a search result looks promising and you need "
        "the complete text for a thorough answer."
    ),
    parameters={
        "type": "object",
        "properties": {
            "page_id": {
                "type": "string",
                "description": "The UUID of the page to retrieve.",
            },
        },
        "required": ["page_id"],
    },
)

FINISH_RETRIEVAL_DEF = ToolDefinition(
    name="finish_retrieval",
    description=(
        "Signal that you have gathered enough context to answer the question. "
        "Call this when you are confident the retrieved sources are sufficient."
    ),
    parameters={
        "type": "object",
        "properties": {},
    },
)


# ── Tool Implementations ──


class SearchDocumentsTool:
    """Wraps HierarchicalSearchUseCase as an agent tool."""

    def __init__(self, hierarchical_search: HierarchicalSearchUseCase) -> None:
        self._search = hierarchical_search

    @property
    def definition(self) -> ToolDefinition:
        return SEARCH_DOCUMENTS_DEF

    async def execute(
        self,
        args: dict[str, Any],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> tuple[list[RetrievalResult], str]:
        """Execute search and return (results, text_summary_for_model)."""
        query = args.get("query", "")
        entity_types = args.get("entity_types") or None
        tags = args.get("tags") or None
        limit = args.get("limit", 10)

        request = HierarchicalSearchRequest(
            query_text=query,
            limit=limit,
            include_chunks=True,
            entity_types_filter=entity_types,
            tags=tags,
            tag_match_mode="any",
        )

        result = await self._search.execute(
            request,
            workspace_id=workspace_id,
            allowed_artifact_ids=allowed_artifact_ids,
        )

        if isinstance(result, Failure):
            return [], f"Search failed: {result.failure()}"

        response = result.unwrap()
        retrieval_results: list[RetrievalResult] = []

        # Build artifact metadata from summary hits
        artifact_meta: dict[str, tuple[list[str], str | None]] = {}
        for sh in response.summary_hits:
            aid = str(sh.artifact_id)
            if aid not in artifact_meta:
                artifact_meta[aid] = (sh.authors or [], sh.presentation_date)

        # Convert chunk hits
        for hit in response.chunk_hits:
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
                    expanded_text=hit.text_preview or "",
                    matched_text=hit.text_preview or "",
                    similarity_score=hit.score,
                    rerank_score=hit.rerank_score,
                    query_source=f"tool:{query[:50]}",
                ),
            )

        # Convert summary hits (top 3)
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
                    query_source=f"tool:{query[:50]}",
                ),
            )

        summary = _format_results_for_model(retrieval_results, query)
        return retrieval_results, summary


class SearchSummariesTool:
    """Wraps SearchSummariesUseCase as an agent tool."""

    def __init__(self, summary_search: SearchSummariesUseCase) -> None:
        self._search = summary_search

    @property
    def definition(self) -> ToolDefinition:
        return SEARCH_SUMMARIES_DEF

    async def execute(
        self,
        args: dict[str, Any],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> tuple[list[RetrievalResult], str]:
        query = args.get("query", "")
        limit = args.get("limit", 5)

        request = SummarySearchRequest(
            query_text=query,
            limit=limit,
        )

        result = await self._search.execute(
            request,
            workspace_id=workspace_id,
            allowed_artifact_ids=allowed_artifact_ids,
        )

        if isinstance(result, Failure):
            return [], f"Summary search failed: {result.failure()}"

        response = result.unwrap()
        retrieval_results: list[RetrievalResult] = []

        for sr in response.results:
            summary_text = sr.summary_text or ""
            retrieval_results.append(
                RetrievalResult(
                    source_type="summary",
                    artifact_id=sr.artifact_id,
                    artifact_title=sr.artifact_title,
                    page_id=sr.entity_id if sr.entity_type == "page" else None,
                    page_index=sr.page_index,
                    expanded_text=summary_text,
                    matched_text=summary_text[:500],
                    similarity_score=sr.similarity_score,
                    query_source=f"tool_summary:{query[:50]}",
                ),
            )

        summary = _format_results_for_model(retrieval_results, query)
        return retrieval_results, summary


class GetPageContentTool:
    """Wraps PageReadModel.get_page_by_id as an agent tool."""

    def __init__(self, page_read_model: PageReadModel) -> None:
        self._pages = page_read_model

    @property
    def definition(self) -> ToolDefinition:
        return GET_PAGE_CONTENT_DEF

    async def execute(
        self,
        args: dict[str, Any],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> tuple[list[RetrievalResult], str]:
        page_id_str = args.get("page_id", "")
        try:
            page_id = UUID(page_id_str)
        except (ValueError, AttributeError):
            return [], f"Invalid page_id: {page_id_str}"

        page = await self._pages.get_page_by_id(page_id)
        if not page:
            return [], f"Page {page_id_str} not found."

        # Access control: check artifact is allowed
        if allowed_artifact_ids and page.artifact_id not in allowed_artifact_ids:
            return [], f"Page {page_id_str} is not accessible."

        full_text = ""
        if page.text_mention and page.text_mention.text:
            full_text = page.text_mention.text

        if not full_text:
            return [], f"Page {page_id_str} has no text content."

        result = RetrievalResult(
            source_type="chunk",
            artifact_id=page.artifact_id,
            artifact_title=None,
            page_id=page_id,
            page_index=page.page_index,
            page_name=page.name,
            expanded_text=full_text[:3000],  # Cap to avoid blowing context
            matched_text=full_text[:500],
            similarity_score=1.0,  # Direct fetch = max relevance
            query_source="tool_page_content",
        )

        summary = f"Page '{page.name or page_id_str}' (page {page.page_index}): {len(full_text)} chars of text content."
        return [result], summary


# ── Tool Registry ──


class ToolRegistry:
    """Holds all retrieval tools and provides lookup + definition list."""

    def __init__(
        self,
        hierarchical_search: HierarchicalSearchUseCase,
        summary_search: SearchSummariesUseCase,
        page_read_model: PageReadModel,
    ) -> None:
        self._tools: dict[str, SearchDocumentsTool | SearchSummariesTool | GetPageContentTool] = {
            "search_documents": SearchDocumentsTool(hierarchical_search),
            "search_summaries": SearchSummariesTool(summary_search),
            "get_page_content": GetPageContentTool(page_read_model),
        }

    @property
    def definitions(self) -> list[ToolDefinition]:
        """All tool definitions including finish_retrieval."""
        return [t.definition for t in self._tools.values()] + [FINISH_RETRIEVAL_DEF]

    async def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> tuple[list[RetrievalResult], str]:
        """Execute a tool by name. Returns (results, summary_for_model)."""
        tool = self._tools.get(tool_name)
        if not tool:
            return [], f"Unknown tool: {tool_name}"

        try:
            return await tool.execute(args, workspace_id, allowed_artifact_ids)
        except Exception as exc:
            log.warning("tool.execution_failed", tool=tool_name, error=str(exc))
            return [], f"Tool {tool_name} failed: {exc!s}"


# ── Helpers ──


def _format_results_for_model(results: list[RetrievalResult], query: str) -> str:
    """Format results as a compact text summary for the LLM."""
    if not results:
        return f"No results found for: {query}"

    lines = [f"Found {len(results)} results for '{query}':"]
    for i, r in enumerate(results[:10], 1):
        title = r.artifact_title or "Unknown"
        score = r.rerank_score if r.rerank_score is not None else r.similarity_score
        if r.source_type == "chunk":
            page_info = f"page {r.page_index}" if r.page_index is not None else ""
            excerpt = r.matched_text[:200].replace("\n", " ")
            lines.append(
                f"  [{i}] {title} ({page_info}, score={score:.2f})"
                f" page_id={r.page_id}: {excerpt}..."
            )
        else:
            excerpt = r.matched_text[:200].replace("\n", " ")
            lines.append(
                f"  [{i}] Summary - {title} (score={score:.2f}): {excerpt}..."
            )

    return "\n".join(lines)
