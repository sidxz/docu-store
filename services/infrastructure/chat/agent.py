"""Custom async agent implementing the ChatAgentPort protocol."""

from __future__ import annotations

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
        max_retries: int = 1,
    ) -> None:
        self._analysis = question_analysis
        self._retrieval = retrieval
        self._synthesis = answer_synthesis
        self._grounding = grounding_verification
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
                "chat.debug.agent.start",
                message=message[:300],
                history_len=len(conversation_history),
                workspace_id=str(workspace_id),
                max_retries=self._max_retries,
            )

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
                    yield AgentEvent(type="token", delta=token)

                synthesis_ms = int((time.monotonic() - t3) * 1000)
                yield AgentEvent(
                    type="step_completed",
                    step="synthesis",
                    status="completed",
                )

                if _debug:
                    log.info(
                        "chat.debug.agent.synthesis_done",
                        duration_ms=synthesis_ms,
                        answer_len=len(draft_answer),
                        tokens_streamed=total_tokens,
                        answer_preview=draft_answer[:300],
                    )

                # ── Step 4: Grounding Verification ──
                t4 = time.monotonic()
                yield AgentEvent(
                    type="step_started",
                    step="verification",
                    status="started",
                    description="Verifying answer is grounded in sources...",
                )

                grounding = await self._grounding.run(draft_answer, sources_text)

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

            elapsed_ms = int((time.monotonic() - start) * 1000)

            if _debug:
                log.info(
                    "chat.debug.agent.complete",
                    total_duration_ms=elapsed_ms,
                    analysis_ms=analysis_ms,
                    total_tokens=total_tokens,
                    citation_count=len(citations),
                    retries=retry_count,
                )

            yield AgentEvent(
                type="done",
                message_id=message_id,
                total_tokens=total_tokens,
                duration_ms=elapsed_ms,
                sources=citations,
            )

        except Exception as exc:
            log.exception("chat.agent.error", error=str(exc))
            yield AgentEvent(
                type="error",
                error_message=f"An error occurred: {exc!s}",
            )
