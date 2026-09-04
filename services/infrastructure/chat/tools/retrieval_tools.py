"""Retrieval tools for the agentic retrieval loop.

Each tool wraps an existing search use case and returns results as
RetrievalResult models + a compact text summary for the LLM + optional
AgentEvent objects (e.g. molecule structured blocks).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from returns.result import Failure

from application.dtos.chat_dtos import AgentEvent, ContentBlockDTO
from application.dtos.search_dtos import HierarchicalSearchRequest, SummarySearchRequest
from application.ports.tool_calling_llm import ToolDefinition
from infrastructure.chat.models import RetrievalResult

if TYPE_CHECKING:
    from application.ports.compound_vector_store import CompoundVectorStore
    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.repositories.page_read_models import PageReadModel
    from application.services.compound_activity_query import CompoundActivityQuery
    from application.use_cases.search_use_cases import (
        HierarchicalSearchUseCase,
        SearchSummariesUseCase,
    )

# Type alias for tool return — (results, summary_for_model, events_to_emit)
ToolResult = tuple[list[RetrievalResult], str, list[AgentEvent]]

log = structlog.get_logger(__name__)

# How much page text a chat search hit carries. The search UI's 500 is a snippet
# length for a clamped card; a model has to actually read this, and a page cut
# mid-table answers the question wrongly rather than partially. Matches
# GetPageContentTool's cap so the two views of a page agree, and matches the HIGH
# tier's per-source cap in ContextAssemblyNode, which does the real limiting.
_CHAT_PREVIEW_CHARS = 3000


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
    ) -> ToolResult:
        """Execute search and return (results, text_summary_for_model, events)."""
        query = args.get("query", "")
        entity_types = args.get("entity_types") or None
        tags = args.get("tags") or None
        limit = args.get("limit", 10)

        # Use strict page-level tag matching for compound queries
        use_page_tags = tags and entity_types and entity_types == ["compound_name"]

        request = HierarchicalSearchRequest(
            query_text=query,
            limit=limit,
            include_chunks=True,
            entity_types_filter=entity_types,
            tags=tags,
            tag_match_mode="page_any" if use_page_tags else "any",
        )

        result = await self._search.execute(
            request,
            workspace_id=workspace_id,
            allowed_artifact_ids=allowed_artifact_ids,
            text_preview_chars=_CHAT_PREVIEW_CHARS,
        )

        if isinstance(result, Failure):
            return [], f"Search failed: {result.failure()}", []

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
        return retrieval_results, summary, []


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
        entity_types = args.get("entity_types") or None
        tags = args.get("tags") or None
        limit = args.get("limit", 5)

        _PAGE_ENTITY_TYPES = {"target", "gene_name", "compound_name"}
        use_page_tags = (
            tags and entity_types and all(et in _PAGE_ENTITY_TYPES for et in entity_types)
        )

        request = SummarySearchRequest(
            query_text=query,
            limit=limit,
            entity_types_filter=entity_types,
            tags=tags,
            tag_match_mode="page_any" if use_page_tags else "any",
        )

        result = await self._search.execute(
            request,
            workspace_id=workspace_id,
            allowed_artifact_ids=allowed_artifact_ids,
        )

        if isinstance(result, Failure):
            return [], f"Summary search failed: {result.failure()}", []

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
        return retrieval_results, summary, []


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
    ) -> ToolResult:
        page_id_str = args.get("page_id", "")
        try:
            page_id = UUID(page_id_str)
        except (ValueError, AttributeError):
            return [], f"Invalid page_id: {page_id_str}", []

        # Scope the fetch to the caller's workspace: page_id is model-controlled
        # (and user-steerable), so an unscoped lookup would return any tenant's
        # page. The allowed_artifact_ids check below is entity-ACL on top and is
        # skipped for full-access members (None) — it is NOT a tenant boundary.
        page = await self._pages.get_page_by_id(page_id, workspace_id=workspace_id)
        if not page:
            return [], f"Page {page_id_str} not found.", []

        # Access control: check artifact is allowed
        if allowed_artifact_ids and page.artifact_id not in allowed_artifact_ids:
            return [], f"Page {page_id_str} is not accessible.", []

        full_text = ""
        if page.text_mention and page.text_mention.text:
            full_text = page.text_mention.text

        if not full_text:
            return [], f"Page {page_id_str} has no text content.", []

        result = RetrievalResult(
            source_type="chunk",
            artifact_id=page.artifact_id,
            artifact_title=None,
            page_id=page_id,
            page_index=page.index,
            page_name=page.name,
            expanded_text=full_text[:_CHAT_PREVIEW_CHARS],  # Cap to avoid blowing context
            # matched_text is what the MEDIUM tier renders (up to 1000 chars), so
            # capping it at 500 truncated the fetch a second time, on a path
            # neither the preview cap nor the dedup merge covers.
            matched_text=full_text[:1000],
            similarity_score=1.0,  # Direct fetch = max relevance
            query_source="tool_page_content",
        )

        summary = f"Page '{page.name or page_id_str}' (page {page.index}): {len(full_text)} chars of text content."
        return [result], summary, []


SEARCH_STRUCTURED_BIOACTIVITY_DEF = ToolDefinition(
    name="search_structured_bioactivity",
    description=(
        "Search for structured bioactivity data (IC50, EC50, Ki, etc.) for a specific compound. "
        "Optionally filter by target. Returns pre-extracted assay data from documents."
    ),
    parameters={
        "type": "object",
        "properties": {
            "compound_name": {
                "type": "string",
                "description": "The compound name to search for bioactivity data.",
            },
            "target_name": {
                "type": "string",
                "description": "Optional target/gene name to filter bioactivity data.",
            },
        },
        "required": ["compound_name"],
    },
)


class SearchStructuredBioactivityTool:
    """Searches pre-extracted bioactivity data from compound tag mentions.

    Delegates the compound page-walk to the shared ``CompoundActivityQuery``
    (same assembly that feeds ``/compounds/{name}/profile``), then renders the
    structured bioactivities as the markdown table the LLM already consumes and
    rides the structured list on ``RetrievalResult.bioactivities`` for the chat
    molecule block (F3).
    """

    def __init__(
        self,
        activity_query: CompoundActivityQuery,
        artifact_read_model: ArtifactReadModel | None = None,
    ) -> None:
        self._activity = activity_query
        self._artifacts = artifact_read_model

    @property
    def definition(self) -> ToolDefinition:
        return SEARCH_STRUCTURED_BIOACTIVITY_DEF

    async def execute(
        self,
        args: dict[str, Any],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> ToolResult:
        compound = args.get("compound_name", "")
        target = args.get("target_name")

        if not compound:
            return [], "No compound name provided.", []

        bios, _synonyms, refs = await self._activity.collect(
            compound,
            workspace_id,
            allowed_artifact_ids,
            target=target,
        )

        if not refs:
            return (
                [],
                f"No accessible documents with compound '{compound}'"
                + (f" and target '{target}'" if target else "")
                + ".",
                [],
            )

        # Markdown table — same shape the LLM already consumes. The Target cell
        # stays blank exactly as before (the reducer never writes a per-bio
        # target, so the old bio_target was always "").
        bio_target = ""
        table_rows = [
            f"| {compound} | {bio_target} | {b.assay_type} | {b.value} {b.unit or ''} |"
            for b in bios
        ]
        if table_rows:
            header = "| Compound | Target | Assay | Value |"
            separator = "|----------|--------|-------|-------|"
            table_text = "\n".join([header, separator, *table_rows[:30]])
        else:
            table_text = f"No structured bioactivity data found for {compound}."

        n_docs = len({r.artifact_id for r in refs})
        results: list[RetrievalResult] = []
        if table_rows:
            anchor = refs[0]
            title, authors, pdate = anchor.artifact_title, [], None
            if self._artifacts:
                try:
                    art = await self._artifacts.get_artifact_by_id(
                        anchor.artifact_id,
                        workspace_id=workspace_id,
                    )
                    if art:
                        title = (
                            art.title_mention.title if art.title_mention else art.source_filename
                        )
                        authors = (
                            [a.name for a in art.author_mentions] if art.author_mentions else []
                        )
                        pdate = (
                            art.presentation_date.date.strftime("%Y-%m-%d")
                            if art.presentation_date
                            else None
                        )
                except Exception:
                    log.warning(
                        "tool.bioactivity.artifact_lookup_failed",
                        artifact_id=str(anchor.artifact_id),
                        exc_info=True,
                    )

            results.append(
                RetrievalResult(
                    source_type="chunk",
                    artifact_id=anchor.artifact_id,
                    artifact_title=title,
                    authors=authors,
                    presentation_date=pdate,
                    page_name="Bioactivity Data",
                    expanded_text=table_text,
                    matched_text=table_text[:500],
                    similarity_score=0.9,
                    query_source=f"tool_bioactivity:{compound}",
                    bioactivities=bios,
                ),
            )

        summary = f"Bioactivity search for '{compound}': {len(table_rows)} data points from {n_docs} documents."
        return results, summary, []


SEARCH_COMPOUND_STRUCTURE_DEF = ToolDefinition(
    name="search_compound_structure",
    description=(
        "Look up a compound by name or ID to get its SMILES structure and find "
        "structurally similar compounds. Use when the user asks about a compound's "
        "structure, SMILES, or wants to see similar molecules. "
        "This renders 2D molecule structures in the response."
    ),
    parameters={
        "type": "object",
        "properties": {
            "compound_name": {
                "type": "string",
                "description": "Compound name or ID (e.g., 'SACC-111', 'Aspirin').",
            },
            "similarity_threshold": {
                "type": "number",
                "description": "Min cosine similarity for related compounds (0-1, default 0.95).",
            },
            "limit": {
                "type": "integer",
                "description": "Max similar compounds to return (default 5).",
            },
        },
        "required": ["compound_name"],
    },
)


class SearchCompoundStructureTool:
    """Looks up a compound by name, retrieves its SMILES, and finds similar structures.

    Emits molecule structured_block events for frontend rendering.
    """

    def __init__(self, compound_vector_store: CompoundVectorStore) -> None:
        self._store = compound_vector_store

    @property
    def definition(self) -> ToolDefinition:
        return SEARCH_COMPOUND_STRUCTURE_DEF

    async def execute(
        self,
        args: dict[str, Any],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> ToolResult:
        from uuid import uuid4

        from domain.value_objects.text_embedding import TextEmbedding

        # "query" is the ReAct fallback key when the LLM outputs a bare string
        # instead of JSON: Action Input: GSK286 → {"query": "GSK286"}
        compound_name = args.get("compound_name") or args.get("query", "")
        compound_name = compound_name.strip()
        threshold = args.get("similarity_threshold", 0.95)
        limit = args.get("limit", 5)

        if not compound_name:
            return [], "No compound name provided.", []

        # 1. Reverse lookup: name → SMILES + vectors
        name_results = await self._store.get_compounds_by_extracted_id(
            extracted_id=compound_name,
            workspace_id=workspace_id,
            allowed_artifact_ids=allowed_artifact_ids,
        )

        if not name_results:
            return [], f"No compound found with ID '{compound_name}' in the document store.", []

        # 2. Build the anchor compound (first unique structure)
        anchor = name_results[0]
        anchor_smiles = anchor.canonical_smiles or anchor.smiles

        # 3. Emit molecule event for the anchor compound
        events: list[AgentEvent] = [
            AgentEvent(
                type="structured_block",
                block=ContentBlockDTO(
                    type="molecule",
                    smiles=anchor_smiles,
                    label=compound_name,
                    page_id=anchor.page_id,
                    artifact_id=anchor.artifact_id,
                ),
            ),
        ]

        # 4. If we have a vector, find similar compounds
        similar_lines: list[str] = []
        anchor_vector = anchor.metadata.get("_vector") if anchor.metadata else None

        if anchor_vector:
            anchor_embedding = TextEmbedding(
                embedding_id=uuid4(),
                vector=anchor_vector,
                model_name="chemberta-77M-mtr",
                dimensions=len(anchor_vector),
            )
            similar_results = await self._store.search_similar_compounds(
                query_embedding=anchor_embedding,
                limit=limit + 1,  # +1 because anchor itself may appear
                score_threshold=threshold,
                workspace_id=workspace_id,
                allowed_artifact_ids=allowed_artifact_ids,
            )

            seen_canonical = {anchor_smiles}
            for sr in similar_results:
                sr_smiles = sr.canonical_smiles or sr.smiles
                if sr_smiles in seen_canonical:
                    continue
                seen_canonical.add(sr_smiles)

                sr_label = sr.extracted_id or sr_smiles[:30]
                pct = f"{sr.score * 100:.0f}%"
                is_exact = sr.score >= 0.9999
                similar_lines.append(f"- {sr_label} (SMILES: {sr_smiles}, similarity: {pct})")

                events.append(
                    AgentEvent(
                        type="structured_block",
                        block=ContentBlockDTO(
                            type="molecule",
                            smiles=sr_smiles,
                            label=f"{sr_label} ({pct} similar)",
                            page_id=sr.page_id if is_exact else None,
                            artifact_id=sr.artifact_id if is_exact else None,
                        ),
                    ),
                )

        # 5. Build retrieval result for LLM context
        expanded_lines = [
            f"Compound: {compound_name}",
            f"Chemical structure (SMILES notation): `{anchor_smiles}`",
            (
                f"Note: The SMILES string above IS the complete molecular structure of "
                f"{compound_name}. SMILES encodes all atoms, bonds, stereochemistry, and "
                f"connectivity. A 2D molecule diagram has been rendered for the user from "
                f"this SMILES."
            ),
            f"Source: artifact {anchor.artifact_id}, page {anchor.page_index}",
        ]
        if similar_lines:
            expanded_lines.append(
                f"\nStructurally similar compounds (≥{threshold * 100:.0f}% similarity):",
            )
            expanded_lines.extend(similar_lines)
        else:
            expanded_lines.append("\nNo structurally similar compounds found above the threshold.")

        retrieval_result = RetrievalResult(
            source_type="chunk",
            artifact_id=anchor.artifact_id,
            artifact_title=None,
            page_id=anchor.page_id,
            page_index=anchor.page_index,
            expanded_text="\n".join(expanded_lines),
            matched_text=f"{compound_name}: {anchor_smiles}",
            similarity_score=1.0,
            query_source=f"tool_structure:{compound_name}",
        )

        summary = (
            f"Compound '{compound_name}' chemical structure found as SMILES: `{anchor_smiles}`. "
            f"The structure is known — a 2D molecule diagram has been rendered for the user. "
            f"{len(similar_lines)} similar compounds above {threshold * 100:.0f}% threshold."
        )

        return [retrieval_result], summary, events


# ── Tool Registry ──


class ToolRegistry:
    """Holds all retrieval tools and provides lookup + definition list."""

    def __init__(
        self,
        hierarchical_search: HierarchicalSearchUseCase,
        summary_search: SearchSummariesUseCase,
        page_read_model: PageReadModel,
        artifact_read_model: ArtifactReadModel | None = None,
        compound_vector_store: CompoundVectorStore | None = None,
        compound_activity_query: CompoundActivityQuery | None = None,
        literature_client: object | None = None,
        literature_only: bool = False,
        stance_llm: object | None = None,
    ) -> None:
        self._tools: dict[str, Any] = {}

        # Literature chat gets exactly one tool. Expressed as an early return
        # rather than a filter over the full set, so the corpus tools are never
        # constructed for it and cannot be reached by a hallucinated tool name.
        if literature_only:
            if literature_client is None:
                msg = "a literature-only ToolRegistry needs a literature client"
                raise ValueError(msg)
            from infrastructure.chat.tools.literature_stats_tools import PlotLiteratureTool
            from infrastructure.chat.tools.literature_tools import SearchLiteratureTool

            self._tools["search_literature"] = SearchLiteratureTool(literature_client)
            self._tools["plot_literature"] = PlotLiteratureTool(
                literature_client, stance_llm=stance_llm,
            )
            return

        self._tools = {
            "search_documents": SearchDocumentsTool(hierarchical_search),
            "search_summaries": SearchSummariesTool(summary_search),
            "get_page_content": GetPageContentTool(page_read_model),
        }
        # Ablation toggles: withholding a tool also disables its deterministic
        # pre-fetch, which is gated on the tool being registered.
        from infrastructure.config import settings

        if compound_activity_query is not None and settings.chat_enable_bioactivity_tool:
            self._tools["search_structured_bioactivity"] = SearchStructuredBioactivityTool(
                activity_query=compound_activity_query,
                artifact_read_model=artifact_read_model,
            )
        if compound_vector_store is not None and settings.chat_enable_structure_tool:
            self._tools["search_compound_structure"] = SearchCompoundStructureTool(
                compound_vector_store=compound_vector_store,
            )

    # Tools that only exist when the reader asked for Stats on this message.
    # Gated here rather than at construction because the registry is a DI
    # singleton and the flag is per-message.
    _STATS_ONLY = frozenset({"plot_literature"})

    @property
    def definitions(self) -> list[ToolDefinition]:
        """All tool definitions including finish_retrieval.

        Stats-only tools are withheld when the turn did not ask for them, so the
        model never sees a tool it may not call.
        """
        from infrastructure.llm.stats_context import stats_enabled

        show_stats = stats_enabled()
        return [
            t.definition
            for name, t in self._tools.items()
            if show_stats or name not in self._STATS_ONLY
        ] + [FINISH_RETRIEVAL_DEF]

    async def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> ToolResult:
        """Execute a tool by name. Returns (results, summary_for_model, events)."""
        tool = self._tools.get(tool_name)
        if not tool:
            return [], f"Unknown tool: {tool_name}", []

        try:
            return await tool.execute(args, workspace_id, allowed_artifact_ids)
        except Exception as exc:
            log.warning("tool.execution_failed", tool=tool_name, error=str(exc))
            return [], f"Tool {tool_name} failed: {exc!s}", []


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
                f" page_id={r.page_id}: {excerpt}...",
            )
        else:
            excerpt = r.matched_text[:200].replace("\n", " ")
            lines.append(f"  [{i}] Summary - {title} (score={score:.2f}): {excerpt}...")

    return "\n".join(lines)
