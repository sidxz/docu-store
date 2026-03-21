"""Stage 5 (Thinking Mode): Lightweight Inline Verification.

Algorithmic citation check first, selective LLM verification only
when coverage is low and query is factual.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import structlog

from infrastructure.chat.models import GroundingResult
from infrastructure.config import settings

if TYPE_CHECKING:
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort
    from infrastructure.chat.models import ContextMetadata, QueryPlan

log = structlog.get_logger(__name__)

_CITATION_RE = re.compile(r"\[(\d{1,2})\]")

# Heuristic: sentences that are likely factual claims (contain numbers, units, names)
_FACTUAL_INDICATORS = re.compile(
    r"(\d+\.?\d*\s*(uM|nM|mM|mg|kg|%|IC50|EC50|Ki|Kd|μM|μg|mol))"
    r"|(\b(was|is|are|were|found|showed|demonstrated|reported|measured|determined)\b)",
    re.IGNORECASE,
)


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
    ) -> GroundingResult:
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
            coverage["ratio"], plan.query_type, context_meta,
        )

        if not needs_llm:
            # Good coverage — skip expensive LLM call
            log.info(
                "chat.inline_verification.skip_llm",
                coverage=coverage["ratio"],
                query_type=plan.query_type,
            )
            return GroundingResult(
                is_grounded=True,
                confidence=min(coverage["ratio"] + 0.1, 1.0),
                supported_claims=[],
                unsupported_claims=[],
                verification_summary=(
                    f"Algorithmic check: {coverage['ratio']:.0%} citation coverage "
                    f"({coverage['cited_sentences']}/{coverage['factual_sentences']} factual sentences cited). "
                    "LLM verification skipped."
                ),
            )

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
        # Split into sentences (rough but effective)
        sentences = re.split(r'(?<=[.!?])\s+', answer.strip())
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

        factual_sentences = 0
        cited_sentences = 0

        for sentence in sentences:
            # Skip headers, list markers, introductory phrases
            if sentence.startswith("#") or sentence.startswith("-") or sentence.startswith("*"):
                continue
            if sentence.endswith(":"):
                continue

            is_factual = bool(_FACTUAL_INDICATORS.search(sentence))
            has_citation = bool(_CITATION_RE.search(sentence))

            if is_factual:
                factual_sentences += 1
                if has_citation:
                    cited_sentences += 1

        ratio = cited_sentences / factual_sentences if factual_sentences > 0 else 1.0

        return {
            "total_sentences": len(sentences),
            "factual_sentences": factual_sentences,
            "cited_sentences": cited_sentences,
            "ratio": ratio,
        }

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

    async def _llm_verify(self, answer: str, sources_text: str) -> GroundingResult:
        """Full LLM grounding verification (same logic as GroundingVerificationNode)."""
        try:
            prompt = await self._prompts.render_prompt(
                "chat_grounding_verification",
                answer=answer,
                sources=sources_text,
            )

            raw = await self._llm.complete(prompt)

            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            data = json.loads(cleaned)
            result = GroundingResult(**data)
            log.info(
                "chat.inline_verification.llm_done",
                is_grounded=result.is_grounded,
                confidence=result.confidence,
            )
            return result

        except (json.JSONDecodeError, Exception) as exc:
            log.warning("chat.inline_verification.llm_fallback", error=str(exc))
            return GroundingResult(
                is_grounded=True,
                confidence=0.5,
                supported_claims=[],
                unsupported_claims=[],
                verification_summary=f"LLM verification failed: {exc!s}",
            )
