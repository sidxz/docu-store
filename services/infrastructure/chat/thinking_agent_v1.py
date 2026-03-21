"""Thinking Mode agent — advanced 5-stage RAG pipeline.

Pipeline: Query Planning → Intelligent Retrieval → Context Assembly
          → Adaptive Synthesis (stream) → Inline Verification

Uses the same AgentEvent SSE schema as the Quick Mode ChatAgent.
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog

from application.dtos.chat_dtos import AgentEvent
from infrastructure.config import settings

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.chat_dtos import ChatMessageDTO, SourceCitationDTO
    from infrastructure.chat.nodes.adaptive_synthesis import AdaptiveSynthesisNode
    from infrastructure.chat.nodes.context_assembly import ContextAssemblyNode
    from infrastructure.chat.nodes.inline_verification import InlineVerificationNode
    from infrastructure.chat.nodes.intelligent_retrieval import IntelligentRetrievalNode
    from infrastructure.chat.nodes.query_planning import QueryPlanningNode

log = structlog.get_logger(__name__)

_CITATION_RE = re.compile(r"\[(\d{1,2})\]")


class ThinkingAgent:
    """Implements ChatAgentPort using the advanced Thinking Mode pipeline."""

    def __init__(
        self,
        query_planning: QueryPlanningNode,
        intelligent_retrieval: IntelligentRetrievalNode,
        context_assembly: ContextAssemblyNode,
        adaptive_synthesis: AdaptiveSynthesisNode,
        inline_verification: InlineVerificationNode,
        max_retries: int = 1,
    ) -> None:
        self._planning = query_planning
        self._retrieval = intelligent_retrieval
        self._assembly = context_assembly
        self._synthesis = adaptive_synthesis
        self._verification = inline_verification
        self._max_retries = max_retries

    async def run(
        self,
        message: str,
        conversation_history: list[ChatMessageDTO],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        start = time.monotonic()
        message_id = uuid4()
        total_tokens = 0
        citations: list[SourceCitationDTO] = []
        _debug = settings.chat_debug

        if _debug:
            log.info(
                "chat.debug.thinking.start",
                message=message[:300],
                history_len=len(conversation_history),
                workspace_id=str(workspace_id),
            )

        try:
            # ── Stage 1: Query Planning ──
            t1 = time.monotonic()
            yield AgentEvent(
                type="step_started",
                step="planning",
                status="started",
                description="Planning query strategy...",
            )

            plan = await self._planning.run(message, conversation_history)

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

            retry_count = 0
            while retry_count <= self._max_retries:
                # ── Stage 2: Intelligent Retrieval ──
                t2 = time.monotonic()
                yield AgentEvent(
                    type="step_started",
                    step="retrieval",
                    status="started",
                    description=(
                        f"Searching documents (strategy: {plan.search_strategy}, "
                        f"queries: {1 + len(plan.sub_queries)})..."
                        + (f" (retry {retry_count})" if retry_count > 0 else "")
                    ),
                )

                retrieval_results = await self._retrieval.run(
                    plan, workspace_id, allowed_artifact_ids,
                )

                retrieval_ms = int((time.monotonic() - t2) * 1000)
                yield AgentEvent(
                    type="step_completed",
                    step="retrieval",
                    status="completed",
                    output=f"Found {len(retrieval_results)} relevant sources",
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

                # ── Stage 4: Adaptive Synthesis (streaming) ──
                t4 = time.monotonic()
                yield AgentEvent(
                    type="step_started",
                    step="synthesis",
                    status="started",
                    description=f"Generating {plan.query_type} answer...",
                )

                draft_answer = ""
                async for token in self._synthesis.run(
                    message, plan, sources_text, context_meta, conversation_history,
                ):
                    draft_answer += token
                    total_tokens += 1
                    yield AgentEvent(type="token", delta=token)

                synthesis_ms = int((time.monotonic() - t4) * 1000)
                yield AgentEvent(
                    type="step_completed",
                    step="synthesis",
                    status="completed",
                )

                # Filter to actually-cited sources
                cited_indices = {int(m) for m in _CITATION_RE.findall(draft_answer)}
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

                grounding = await self._verification.run(
                    draft_answer, sources_text, plan, context_meta,
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

                # Retry: only re-run synthesis (Stage 4) with augmented prompt
                log.info(
                    "chat.thinking.retry",
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

            elapsed_ms = int((time.monotonic() - start) * 1000)

            log.info(
                "chat.thinking.citation_filter",
                retrieved=len(citations),
                cited_indices=sorted(cited_indices),
                used=len(used_citations),
            )

            yield AgentEvent(
                type="done",
                message_id=message_id,
                total_tokens=total_tokens,
                duration_ms=elapsed_ms,
                sources=used_citations,
            )

        except Exception as exc:
            log.exception("chat.thinking.error", error=str(exc))
            yield AgentEvent(
                type="error",
                error_message=f"An error occurred: {exc!s}",
            )
