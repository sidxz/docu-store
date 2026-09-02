"""Stage 5 (Thinking Mode): Lightweight Inline Verification.

Algorithmic citation check first, selective LLM verification only
when coverage is low and query is factual.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from infrastructure.chat.models import GroundingResult
from infrastructure.chat.utils import compute_citation_coverage, strip_markdown_fences
from infrastructure.config import settings

if TYPE_CHECKING:
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort
    from infrastructure.chat.models import ContextMetadata, QueryPlan

log = structlog.get_logger(__name__)


class InlineVerificationNode:
    """Verify grounding with algorithmic check + selective LLM fallback."""

    def __init__(
        self,
        llm_client: LLMClientPort,
        prompt_repository: PromptRepositoryPort,
    ) -> None:
        self._llm = llm_client
        self._prompts = prompt_repository

    async def run(
        self,
        answer: str,
        sources_text: str,
        plan: QueryPlan,
        context_meta: ContextMetadata,
    ) -> tuple[GroundingResult, str]:
        _debug = settings.chat_debug

        # Step 1: Algorithmic citation check
        coverage = self._compute_citation_coverage(answer)

        if _debug:
            log.info(
                "chat.debug.inline_verification.coverage",
                citation_coverage=coverage["ratio"],
                total_sentences=coverage["total_sentences"],
                factual_sentences=coverage["factual_sentences"],
                cited_sentences=coverage["cited_sentences"],
            )

        # Step 2: Decide if LLM verification is needed
        needs_llm = self._needs_llm_verification(
            coverage["ratio"],
            plan.query_type,
            context_meta,
        )

        if not needs_llm:
            # Good coverage — skip expensive LLM call
            log.info(
                "chat.inline_verification.skip_llm",
                coverage=coverage["ratio"],
                query_type=plan.query_type,
            )
            summary = (
                f"Algorithmic check: {coverage['ratio']:.0%} citation coverage "
                f"({coverage['cited_sentences']}/{coverage['factual_sentences']} factual sentences cited). "
                "LLM verification skipped."
            )
            return GroundingResult(
                is_grounded=True,
                confidence=min(coverage["ratio"] + 0.1, 1.0),
                supported_claims=[],
                unsupported_claims=[],
                verification_summary=summary,
            ), summary

        # Step 3: Full LLM grounding check (same as Quick Mode)
        log.info(
            "chat.inline_verification.llm_triggered",
            coverage=coverage["ratio"],
            query_type=plan.query_type,
            avg_relevance=context_meta.avg_relevance_score,
        )
        return await self._llm_verify(answer, sources_text)

    def _compute_citation_coverage(self, answer: str) -> dict:
        """Parse answer, classify sentences, compute coverage ratio."""
        return compute_citation_coverage(answer)

    def _needs_llm_verification(
        self,
        coverage_ratio: float,
        query_type: str,
        context_meta: ContextMetadata,
    ) -> bool:
        """Determine if LLM verification is warranted."""
        cov_threshold = settings.chat_verification_coverage_threshold
        rel_threshold = settings.chat_verification_relevance_threshold

        # Only trigger LLM check when BOTH conditions met AND query is factual
        if coverage_ratio >= cov_threshold:
            return False

        if query_type not in ("factual", "comparative"):
            return False

        if context_meta.avg_relevance_score >= rel_threshold:
            # Low coverage but high relevance — might just be a stylistic issue
            return False

        return True

    async def _llm_verify(self, answer: str, sources_text: str) -> tuple[GroundingResult, str]:
        """Full LLM grounding verification (same logic as GroundingVerificationNode).

        Returns (result, raw_llm_output).
        """
        try:
            prompt = await self._prompts.render_prompt(
                "chat_grounding_verification",
                answer=answer,
                sources=sources_text,
            )

            raw = await self._llm.complete(prompt)

            cleaned = strip_markdown_fences(raw)

            data = json.loads(cleaned)
            result = GroundingResult(**data)
            log.info(
                "chat.inline_verification.llm_done",
                is_grounded=result.is_grounded,
                confidence=result.confidence,
            )
            return result, raw

        except (json.JSONDecodeError, Exception) as exc:
            log.warning("chat.inline_verification.llm_fallback", error=str(exc))
            fallback_summary = f"LLM verification failed: {exc!s}"
            return GroundingResult(
                is_grounded=True,
                confidence=0.5,
                supported_claims=[],
                unsupported_claims=[],
                verification_summary=fallback_summary,
            ), fallback_summary
