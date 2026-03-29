"""Custom async agent implementing the ChatAgentPort protocol."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog

from application.dtos.chat_dtos import AgentEvent
from infrastructure.chat.utils import CITATION_RE, extract_cited_indices
from infrastructure.config import settings
from infrastructure.llm.token_counter import TokenCounter

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.chat_dtos import ChatMessageDTO, SourceCitationDTO
    from infrastructure.chat.nodes.answer_formatting import AnswerFormattingNode
    from infrastructure.chat.nodes.answer_synthesis import AnswerSynthesisNode
    from infrastructure.chat.nodes.grounding_verification import GroundingVerificationNode
    from infrastructure.chat.nodes.question_analysis import QuestionAnalysisNode
    from infrastructure.chat.nodes.retrieval import RetrievalNode

log = structlog.get_logger(__name__)


class ChatAgent:
    """Implements ChatAgentPort using direct async orchestration.

    Pipeline: Question Analysis -> Retrieval -> Synthesis (streaming) -> Grounding Verification
    with a conditional retry loop if grounding fails.
    """

    def __init__(
        self,
        question_analysis: QuestionAnalysisNode,
        retrieval: RetrievalNode,
        answer_synthesis: AnswerSynthesisNode,
        grounding_verification: GroundingVerificationNode,
        answer_formatting: AnswerFormattingNode,
        max_retries: int = 1,
    ) -> None:
        self._analysis = question_analysis
        self._retrieval = retrieval
        self._synthesis = answer_synthesis
        self._grounding = grounding_verification
        self._formatting = answer_formatting
        self._max_retries = max_retries

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
                "chat.debug.agent.start",
                message=message[:300],
                history_len=len(conversation_history),
                workspace_id=str(workspace_id),
                max_retries=self._max_retries,
            )

        token_counter.__enter__()
        try:
            # ── Step 1: Question Analysis ──
            t1 = time.monotonic()
            yield AgentEvent(
                type="step_started",
                step="analysis",
                status="started",
                description="Analyzing your question...",
            )

            analysis = await self._analysis.run(message, conversation_history)

            analysis_ms = int((time.monotonic() - t1) * 1000)
            yield AgentEvent(
                type="step_completed",
                step="analysis",
                status="completed",
                output=f"Query type: {analysis.query_type}. Strategy: {analysis.search_strategy}. "
                f"Entities: {', '.join(analysis.entities[:5]) if analysis.entities else 'none'}",
            )

            if _debug:
                log.info(
                    "chat.debug.agent.analysis_done",
                    duration_ms=analysis_ms,
                    query_type=analysis.query_type,
                    strategy=analysis.search_strategy,
                    reformulated_query=analysis.reformulated_query,
                    entities=analysis.entities,
                    smiles_detected=analysis.smiles_detected,
                )

            # Emit query_context for NER accumulation
            smiles_ctx = analysis.smiles_context
            yield AgentEvent(
                type="query_context",
                query_context_entities=[],  # Quick mode has no NER
                query_context_type=analysis.query_type,
                query_context_reformulated=analysis.reformulated_query,
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

            retry_count = 0
            while retry_count <= self._max_retries:
                # ── Step 2: Retrieval ──
                t2 = time.monotonic()
                yield AgentEvent(
                    type="step_started",
                    step="retrieval",
                    status="started",
                    description=f"Searching documents (strategy: {analysis.search_strategy})..."
                    + (f" (retry {retry_count})" if retry_count > 0 else ""),
                )

                citations, sources_text = await self._retrieval.run(
                    analysis,
                    workspace_id,
                    allowed_artifact_ids,
                )

                retrieval_ms = int((time.monotonic() - t2) * 1000)
                yield AgentEvent(
                    type="step_completed",
                    step="retrieval",
                    status="completed",
                    output=f"Found {len(citations)} relevant sources",
                )

                yield AgentEvent(
                    type="retrieval_results",
                    sources=citations,
                )

                if _debug:
                    log.info(
                        "chat.debug.agent.retrieval_done",
                        duration_ms=retrieval_ms,
                        citation_count=len(citations),
                        sources_text_len=len(sources_text),
                        retry=retry_count,
                    )

                # ── Step 3: Answer Synthesis (streaming) ──
                t3 = time.monotonic()
                yield AgentEvent(
                    type="step_started",
                    step="synthesis",
                    status="started",
                    description="Generating answer from sources...",
                )

                draft_answer = ""
                async for token in self._synthesis.run(
                    message,
                    analysis,
                    sources_text,
                    conversation_history,
                ):
                    draft_answer += token
                    total_tokens += 1

                synthesis_ms = int((time.monotonic() - t3) * 1000)
                yield AgentEvent(
                    type="step_completed",
                    step="synthesis",
                    status="completed",
                    thinking_content=draft_answer,
                )

                # Determine which citations were actually used in the answer
                cited_indices = extract_cited_indices(draft_answer)
                used_citations = [c for c in citations if c.citation_index in cited_indices]
                # Build source text for grounding using only cited sources
                used_sources_text = _build_cited_sources_text(used_citations, sources_text)

                if _debug:
                    log.info(
                        "chat.debug.agent.synthesis_done",
                        duration_ms=synthesis_ms,
                        answer_len=len(draft_answer),
                        tokens_streamed=total_tokens,
                        answer_preview=draft_answer[:300],
                        cited_indices=sorted(cited_indices),
                        total_retrieved=len(citations),
                        actually_used=len(used_citations),
                    )

                # ── Step 4: Grounding Verification (against cited sources only) ──
                t4 = time.monotonic()
                yield AgentEvent(
                    type="step_started",
                    step="verification",
                    status="started",
                    description=f"Verifying {len(used_citations)} cited sources...",
                )

                grounding = await self._grounding.run(draft_answer, used_sources_text)

                verification_ms = int((time.monotonic() - t4) * 1000)
                yield AgentEvent(
                    type="step_completed",
                    step="verification",
                    status="completed",
                    output=f"Grounded: {grounding.is_grounded} "
                    f"(confidence: {grounding.confidence:.0%})"
                    + (
                        f". Unsupported: {', '.join(grounding.unsupported_claims[:3])}"
                        if grounding.unsupported_claims
                        else ""
                    ),
                )

                # Emit structured grounding result for the frontend
                yield AgentEvent(
                    type="grounding_result",
                    grounding_is_grounded=grounding.is_grounded,
                    grounding_confidence=grounding.confidence,
                )

                if _debug:
                    log.info(
                        "chat.debug.agent.verification_done",
                        duration_ms=verification_ms,
                        is_grounded=grounding.is_grounded,
                        confidence=grounding.confidence,
                        supported=grounding.supported_claims[:3],
                        unsupported=grounding.unsupported_claims[:3],
                    )

                if grounding.is_grounded or retry_count >= self._max_retries:
                    break

                # Retry: create refined analysis (immutable)
                log.info(
                    "chat.agent.retry",
                    retry=retry_count + 1,
                    unsupported=grounding.unsupported_claims,
                )
                analysis = analysis.model_copy(
                    update={
                        "reformulated_query": (
                            f"{analysis.reformulated_query} "
                            f"(focus on: {', '.join(grounding.unsupported_claims[:3])})"
                        ),
                    },
                )
                retry_count += 1

            # ── Step 5: Answer Formatting ──
            t5 = time.monotonic()
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

            formatting_ms = int((time.monotonic() - t5) * 1000)
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
                    "chat.debug.agent.formatting_done",
                    duration_ms=formatting_ms,
                    formatted_len=len(formatted_answer),
                )

            elapsed_ms = int((time.monotonic() - start) * 1000)

            if _debug:
                log.info(
                    "chat.debug.agent.complete",
                    total_duration_ms=elapsed_ms,
                    analysis_ms=analysis_ms,
                    total_tokens=total_tokens,
                    retrieved_count=len(citations),
                    cited_count=len(used_citations),
                    retries=retry_count,
                )

            # done event carries only the actually-cited sources
            log.info(
                "chat.agent.citation_filter",
                retrieved=len(citations),
                cited_indices=sorted(cited_indices),
                used=len(used_citations),
            )
            api_tokens = token_counter.total_tokens
            yield AgentEvent(
                type="done",
                message_id=message_id,
                total_tokens=api_tokens if api_tokens > 0 else total_tokens,
                duration_ms=elapsed_ms,
                sources=used_citations,
                prompt_tokens=token_counter.prompt_tokens,
                completion_tokens=token_counter.completion_tokens,
            )

        except Exception as exc:
            log.exception("chat.agent.error", error=str(exc))
            yield AgentEvent(
                type="error",
                error_message=f"An error occurred: {exc!s}",
            )
        finally:
            token_counter.__exit__(None, None, None)


def _build_cited_sources_text(
    used_citations: list,
    full_sources_text: str,
) -> str:
    """Build source text containing only the cited sources for grounding verification.

    Parses the formatted sources text (which has [N] headers) and keeps only
    sections matching used citation indices. Falls back to full text if parsing fails.
    """
    if not used_citations:
        return full_sources_text

    used_indices = {c.citation_index for c in used_citations}
    sections = full_sources_text.split("\n\n")
    kept = []
    for section in sections:
        # Each section starts with [N] — extract the index
        match = CITATION_RE.match(section.strip())
        if match and int(match.group(1)) in used_indices:
            kept.append(section)
        elif not match:
            # Non-indexed section (header, etc.) — keep it
            kept.append(section)

    return "\n\n".join(kept) if kept else full_sources_text
