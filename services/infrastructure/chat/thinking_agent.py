"""Thinking Mode agent — advanced 5-stage RAG pipeline (v2 with agentic retrieval).

Pipeline: Query Planning → Agentic Retrieval Loop → Context Assembly
          → Adaptive Synthesis (stream) → Inline Verification

Factual-mode optimisation: when NER filters produce sufficient results,
the unfiltered seed search is skipped. If verification fails, the retry
broadens search scope (includes unfiltered) before falling back to the
standard query-augmentation retry strategy.

Uses the same AgentEvent SSE schema as the Quick Mode ChatAgent.
"""

from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog

from application.dtos.chat_dtos import AgentEvent
from infrastructure.chat.utils import extract_cited_indices
from infrastructure.config import settings
from infrastructure.llm.token_counter import TokenCounter

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.chat_dtos import ChatMessageDTO, SourceCitationDTO
    from application.ports.blob_store import BlobStore
    from application.ports.repositories.tag_dictionary_read_model import TagDictionaryReadModel
    from infrastructure.chat.models import QueryPlan
    from infrastructure.chat.nodes.adaptive_synthesis import AdaptiveSynthesisNode
    from infrastructure.chat.nodes.agentic_retrieval import AgenticRetrievalNode
    from infrastructure.chat.nodes.answer_formatting import AnswerFormattingNode
    from infrastructure.chat.nodes.context_assembly import ContextAssemblyNode
    from infrastructure.chat.nodes.inline_verification import InlineVerificationNode
    from infrastructure.chat.nodes.query_planning import QueryPlanningNode

log = structlog.get_logger(__name__)


class ThinkingAgent:
    """Implements ChatAgentPort using the advanced Thinking Mode pipeline (v2)."""

    def __init__(
        self,
        query_planning: QueryPlanningNode,
        agentic_retrieval: AgenticRetrievalNode,
        context_assembly: ContextAssemblyNode,
        adaptive_synthesis: AdaptiveSynthesisNode,
        inline_verification: InlineVerificationNode,
        answer_formatting: AnswerFormattingNode,
        tag_dictionary: TagDictionaryReadModel,
        max_retries: int = 1,
        blob_store: BlobStore | None = None,
        include_images: bool = False,
    ) -> None:
        self._planning = query_planning
        self._retrieval = agentic_retrieval
        self._assembly = context_assembly
        self._synthesis = adaptive_synthesis
        self._verification = inline_verification
        self._formatting = answer_formatting
        self._tag_dict = tag_dictionary
        self._max_retries = max_retries
        self._blob_store = blob_store
        self._include_images = include_images

    async def run(
        self,
        message: str,
        conversation_history: list[ChatMessageDTO],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None = None,
        previous_citations: list[SourceCitationDTO] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        start = time.monotonic()
        message_id = uuid4()
        total_tokens = 0
        citations: list[SourceCitationDTO] = []
        _debug = settings.chat_debug
        token_counter = TokenCounter()

        if _debug:
            log.info(
                "chat.debug.thinking.start",
                message=message[:300],
                history_len=len(conversation_history),
                workspace_id=str(workspace_id),
                has_previous_citations=previous_citations is not None,
                previous_citation_count=len(previous_citations) if previous_citations else 0,
            )

        # Activate token counter for the entire pipeline run
        token_counter.__enter__()

        try:
            # ── Stage 1: Query Planning ──
            t1 = time.monotonic()
            yield AgentEvent(
                type="step_started",
                step="planning",
                status="started",
                description="Planning query strategy...",
            )

            plan, planning_llm_output = await self._planning.run(message, conversation_history)

            # Expand partial author names via tag dictionary prefix search
            if plan.author_mentions:
                plan = await self._expand_author_mentions(plan, workspace_id)

            planning_ms = int((time.monotonic() - t1) * 1000)
            ner_desc = ", ".join(
                f"{f.entity_text} ({f.entity_type})" for f in plan.ner_entity_filters
            )
            author_desc = ", ".join(plan.author_mentions) if plan.author_mentions else ""
            sub_q_desc = f" Sub-queries: {len(plan.sub_queries)}." if plan.sub_queries else ""

            yield AgentEvent(
                type="step_completed",
                step="planning",
                status="completed",
                output=(
                    f"Type: {plan.query_type}. Strategy: {plan.search_strategy}. "
                    f"Confidence: {plan.confidence:.0%}.{sub_q_desc}"
                    + (f" NER filters: {ner_desc}." if ner_desc else "")
                    + (f" Authors: {author_desc}." if author_desc else "")
                ),
                thinking_content=planning_llm_output or None,
                thinking_label="Query Analysis",
            )

            if _debug:
                log.info(
                    "chat.debug.thinking.planning_done",
                    duration_ms=planning_ms,
                    query_type=plan.query_type,
                    strategy=plan.search_strategy,
                    confidence=plan.confidence,
                    reformulated=plan.reformulated_query,
                    sub_queries=plan.sub_queries,
                    ner_filters=[(f.entity_text, f.entity_type) for f in plan.ner_entity_filters],
                    authors=plan.author_mentions,
                )

            # Emit query_context for NER accumulation
            smiles_ctx = plan.smiles_context
            yield AgentEvent(
                type="query_context",
                query_context_entities=[
                    {"entity_text": f.entity_text, "entity_type": f.entity_type}
                    for f in plan.ner_entity_filters
                ],
                query_context_authors=plan.author_mentions,
                query_context_type=plan.query_type,
                query_context_reformulated=plan.reformulated_query,
                query_context_smiles=smiles_ctx.detected if smiles_ctx else None,
                query_context_smiles_resolved=[
                    {
                        "canonical_smiles": c.canonical_smiles,
                        "extracted_ids": c.extracted_ids,
                        "best_similarity": c.best_similarity,
                        "mode": smiles_ctx.mode,
                    }
                    for c in smiles_ctx.resolved
                ]
                if smiles_ctx and smiles_ctx.resolved
                else None,
            )

            # Factual + NER filters → try filtered-only first, broaden on retry.
            # Compound queries with resolved SMILES also use strict mode — the
            # resolved compound name is in NER filters and should scope retrieval.
            has_filters = bool(plan.ner_entity_filters or plan.author_mentions)
            has_resolved_smiles = bool(plan.smiles_context and plan.smiles_context.resolved)
            skipped_unfiltered = (
                plan.query_type in ("factual", "compound")
                and has_filters
                and settings.chat_factual_skip_unfiltered
            ) or (has_resolved_smiles and has_filters)

            retry_count = 0
            while retry_count <= self._max_retries:
                # ── Stage 2: Agentic Retrieval (iterative) ──
                t2 = time.monotonic()
                yield AgentEvent(
                    type="step_started",
                    step="retrieval",
                    status="started",
                    description=(
                        "Searching documents (agentic mode)..."
                        + (f" (retry {retry_count})" if retry_count > 0 else "")
                    ),
                )

                retrieval_results = []
                async for kind, payload in self._retrieval.run(
                    plan,
                    workspace_id,
                    allowed_artifact_ids,
                    question=message,
                    skip_unfiltered_seed=skipped_unfiltered,
                    previous_citations=previous_citations,
                ):
                    if kind == "event":
                        yield payload  # Forward step events to SSE
                    elif kind == "results":
                        retrieval_results = payload

                retrieval_ms = int((time.monotonic() - t2) * 1000)
                yield AgentEvent(
                    type="step_completed",
                    step="retrieval",
                    status="completed",
                    output=f"Found {len(retrieval_results)} relevant sources ({retrieval_ms}ms)",
                )

                if _debug:
                    log.info(
                        "chat.debug.thinking.retrieval_done",
                        duration_ms=retrieval_ms,
                        result_count=len(retrieval_results),
                        retry=retry_count,
                    )

                # ── Stage 3: Context Assembly ──
                t3 = time.monotonic()
                yield AgentEvent(
                    type="step_started",
                    step="assembly",
                    status="started",
                    description="Assembling and ranking context...",
                )

                citations, sources_text, context_meta = self._assembly.run(
                    retrieval_results,
                )

                assembly_ms = int((time.monotonic() - t3) * 1000)
                yield AgentEvent(
                    type="step_completed",
                    step="assembly",
                    status="completed",
                    output=(
                        f"Assembled {context_meta.total_sources} sources from "
                        f"{context_meta.unique_artifacts} documents "
                        f"({context_meta.high_relevance_count} high relevance)"
                    ),
                )

                yield AgentEvent(
                    type="retrieval_results",
                    sources=citations,
                )

                if _debug:
                    log.info(
                        "chat.debug.thinking.assembly_done",
                        duration_ms=assembly_ms,
                        total_sources=context_meta.total_sources,
                        high_relevance=context_meta.high_relevance_count,
                        avg_score=context_meta.avg_relevance_score,
                        unique_artifacts=context_meta.unique_artifacts,
                    )

                # ── Stage 3.5: Image Loading (Deep Thinking only) ──
                images_b64: list[str] | None = None
                if self._include_images and self._blob_store:
                    yield AgentEvent(
                        type="step_started",
                        step="image_loading",
                        status="started",
                        description="Loading page images for visual analysis...",
                    )
                    images_b64 = await self._load_page_images(citations)
                    yield AgentEvent(
                        type="step_completed",
                        step="image_loading",
                        status="completed",
                        output=f"Loaded {len(images_b64)} page images",
                    )
                    if _debug:
                        log.info(
                            "chat.debug.thinking.images_loaded",
                            count=len(images_b64),
                        )

                # ── Stage 4: Adaptive Synthesis (streaming) ──
                t4 = time.monotonic()
                yield AgentEvent(
                    type="step_started",
                    step="synthesis",
                    status="started",
                    description=f"Generating {plan.query_type} answer...",
                )

                draft_answer = ""
                async for kind, payload in self._synthesis.run(
                    message,
                    plan,
                    sources_text,
                    context_meta,
                    conversation_history,
                    images_b64=images_b64,
                ):
                    if kind == "event":
                        yield payload  # Forward thinking events (e.g. answer plan)
                    else:
                        draft_answer += payload
                        total_tokens += 1

                synthesis_ms = int((time.monotonic() - t4) * 1000)
                yield AgentEvent(
                    type="step_completed",
                    step="synthesis",
                    status="completed",
                )

                # Filter to actually-cited sources
                cited_indices = extract_cited_indices(draft_answer)
                used_citations = [c for c in citations if c.citation_index in cited_indices]

                if _debug:
                    log.info(
                        "chat.debug.thinking.synthesis_done",
                        duration_ms=synthesis_ms,
                        answer_len=len(draft_answer),
                        tokens_streamed=total_tokens,
                        cited_indices=sorted(cited_indices),
                        total_citations=len(citations),
                        used_citations=len(used_citations),
                    )

                # ── Stage 5: Inline Verification ──
                t5 = time.monotonic()
                yield AgentEvent(
                    type="step_started",
                    step="verification",
                    status="started",
                    description="Verifying citations...",
                )

                grounding, verification_llm_output = await self._verification.run(
                    draft_answer,
                    sources_text,
                    plan,
                    context_meta,
                )

                verification_ms = int((time.monotonic() - t5) * 1000)
                yield AgentEvent(
                    type="step_completed",
                    step="verification",
                    status="completed",
                    output=(
                        f"Grounded: {grounding.is_grounded} "
                        f"(confidence: {grounding.confidence:.0%})"
                        + (
                            f". Unsupported: {', '.join(grounding.unsupported_claims[:3])}"
                            if grounding.unsupported_claims
                            else ""
                        )
                    ),
                    thinking_content=verification_llm_output or None,
                    thinking_label="Citation Verification",
                )

                yield AgentEvent(
                    type="grounding_result",
                    grounding_is_grounded=grounding.is_grounded,
                    grounding_confidence=grounding.confidence,
                )

                if _debug:
                    log.info(
                        "chat.debug.thinking.verification_done",
                        duration_ms=verification_ms,
                        is_grounded=grounding.is_grounded,
                        confidence=grounding.confidence,
                    )

                if grounding.is_grounded or retry_count >= self._max_retries:
                    break

                if skipped_unfiltered:
                    # Retry strategy A: broaden search by including unfiltered results
                    log.info(
                        "chat.thinking.retry_broaden",
                        retry=retry_count + 1,
                        unsupported=grounding.unsupported_claims,
                    )
                    skipped_unfiltered = False  # Next pass includes unfiltered seed
                else:
                    # Retry strategy B: augment query with unsupported claims
                    log.info(
                        "chat.thinking.retry_augment",
                        retry=retry_count + 1,
                        unsupported=grounding.unsupported_claims,
                    )
                    plan = plan.model_copy(
                        update={
                            "reformulated_query": (
                                f"{plan.reformulated_query} "
                                f"(focus on: {', '.join(grounding.unsupported_claims[:3])})"
                            ),
                        },
                    )
                retry_count += 1

            # ── Stage 6: Answer Formatting ──
            t6 = time.monotonic()
            yield AgentEvent(
                type="step_started",
                step="formatting",
                status="started",
                description="Formatting answer...",
            )
            formatted_answer = ""
            async for token in self._formatting.run(message, draft_answer):
                formatted_answer += token
                total_tokens += 1
                yield AgentEvent(type="token", delta=token)

            formatting_ms = int((time.monotonic() - t6) * 1000)
            yield AgentEvent(
                type="step_completed",
                step="formatting",
                status="completed",
                output=f"Formatted ({formatting_ms}ms)",
            )

            # Re-extract citations from formatted answer
            cited_indices = extract_cited_indices(formatted_answer)
            used_citations = [c for c in citations if c.citation_index in cited_indices]

            if _debug:
                log.info(
                    "chat.debug.thinking.formatting_done",
                    duration_ms=formatting_ms,
                    formatted_len=len(formatted_answer),
                )

            elapsed_ms = int((time.monotonic() - start) * 1000)

            log.info(
                "chat.thinking.citation_filter",
                retrieved=len(citations),
                cited_indices=sorted(cited_indices),
                used=len(used_citations),
            )

            # Use real API token counts if available, fall back to streamed count
            api_tokens = token_counter.total_tokens
            yield AgentEvent(
                type="done",
                message_id=message_id,
                total_tokens=api_tokens if api_tokens > 0 else total_tokens,
                duration_ms=elapsed_ms,
                sources=used_citations,
                # Carry prompt/completion breakdown for persistence
                prompt_tokens=token_counter.prompt_tokens,
                completion_tokens=token_counter.completion_tokens,
            )

        except Exception as exc:
            log.exception("chat.thinking.error", error=str(exc))
            yield AgentEvent(
                type="error",
                error_message=f"An error occurred: {exc!s}",
            )
        finally:
            token_counter.__exit__(None, None, None)

    async def _expand_author_mentions(
        self,
        plan: QueryPlan,
        workspace_id: UUID,
    ) -> QueryPlan:
        """Expand partial author names (e.g. 'Tanya') to full names ('Tanya Parish')
        using tag dictionary prefix search.
        """
        expanded: list[str] = []
        for name in plan.author_mentions:
            try:
                suggestions = await self._tag_dict.suggest_tags(
                    query=name,
                    workspace_id=workspace_id,
                    limit=5,
                )
                # Keep author-type suggestions that start with the partial name
                matches = [
                    s["tag"]
                    for s in suggestions
                    if s.get("entity_type") == "author"
                    and s["tag"].lower().startswith(name.lower())
                ]
                log.info(
                    "chat.thinking.author_suggest",
                    name=name,
                    matches=matches,
                )
                if matches:
                    expanded.extend(matches)
                    if name.lower() not in {m.lower() for m in matches}:
                        expanded.append(name)
                else:
                    expanded.append(name)
            except Exception:
                log.warning(
                    "chat.thinking.author_expand_failed",
                    name=name,
                    exc_info=True,
                )
                expanded.append(name)

        # Deduplicate preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for a in expanded:
            key = a.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(a)

        if deduped != plan.author_mentions:
            log.info(
                "chat.thinking.author_expanded",
                original=plan.author_mentions,
                expanded=deduped,
            )
            return plan.model_copy(update={"author_mentions": deduped})
        return plan

    async def _load_page_images(
        self,
        citations: list[SourceCitationDTO],
    ) -> list[str]:
        """Load page PNG images for the most relevant cited pages."""
        assert self._blob_store is not None  # noqa: S101

        max_images = settings.chat_deep_thinking_max_images

        # Deduplicate by (artifact_id, page_index), keep highest score
        seen: set[tuple[str, int]] = set()
        candidates: list[SourceCitationDTO] = []
        for c in citations:
            if c.page_index is None:
                continue
            key = (str(c.artifact_id), c.page_index)
            if key not in seen:
                seen.add(key)
                candidates.append(c)

        # Sort by relevance, take top N
        candidates.sort(
            key=lambda c: c.similarity_score or 0.0,
            reverse=True,
        )
        candidates = candidates[:max_images]

        # Load images in parallel via thread pool (blob store is sync)
        blob_store = self._blob_store

        async def _load_one(c: SourceCitationDTO) -> str | None:
            image_key = f"artifacts/{c.artifact_id}/pages/{c.page_index}.png"
            try:
                exists = await asyncio.to_thread(blob_store.exists, image_key)
                if not exists:
                    return None
                raw = await asyncio.to_thread(blob_store.get_bytes, image_key)
                return base64.b64encode(raw).decode("ascii")
            except Exception:
                log.warning(
                    "chat.thinking.image_load_failed",
                    image_key=image_key,
                    exc_info=True,
                )
                return None

        results = await asyncio.gather(*[_load_one(c) for c in candidates])
        images = [img for img in results if img is not None]

        log.info(
            "chat.thinking.images_loaded",
            requested=len(candidates),
            loaded=len(images),
        )
        return images
