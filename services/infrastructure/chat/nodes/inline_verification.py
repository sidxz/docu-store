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
from infrastructure.chat.utils import CITATION_RE, strip_markdown_fences
from infrastructure.config import settings

if TYPE_CHECKING:
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort
    from infrastructure.chat.models import ContextMetadata, QueryPlan

log = structlog.get_logger(__name__)

# Heuristic: sentences that are likely factual claims (contain numbers, units, names)
_FACTUAL_INDICATORS = re.compile(
    r"(\d+\.?\d*\s*(uM|nM|mM|mg|kg|%|IC50|EC50|Ki|Kd|μM|μg|mol))"
    r"|(\b(was|is|are|were|found|showed|demonstrated|reported|measured|determined)\b)",
    re.IGNORECASE,
)

# A citation trailing its sentence — "…0.19 µM. [2]" — splits off as a fragment
# of its own, which the length filter below would then discard, leaving the claim
# it supports counted as uncited. Merge such fragments back into the sentence
# they belong to. Done after the split rather than by rewriting the answer: the
# boundaries are already decided here, so this cannot create or destroy one, and
# cannot drag a citation backward across an abbreviation's period the way a
# text-level substitution does.
#
# Only a citation isolated as its OWN fragment gets rescued this way. A citation
# trailing the middle of a multi-sentence answer stays glued to the sentence that
# follows it instead — an accepted undercount, pinned by
# test_a_mid_answer_trailing_citation_is_not_attributed_backwards. Pulling a
# leading citation run back onto the previous fragment would rescue that shape
# too, but it also reintroduces the abbreviation regression ("…, i.e. [1]
# Compound 44 …"), since a fragment boundary made by an abbreviation's period is
# indistinguishable from a real one at this layer. The undercount is the safe
# direction: it can only trigger more verification than needed, never less.
_CITATION_ONLY = re.compile(r"(?:\[\d{1,2}(?:\s*,\s*\d{1,2})*\]\s*)+")


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
        # Split into sentences (rough but effective)
        split = re.split(r"(?<=[.!?])\s+", answer.strip())

        merged: list[str] = []
        for fragment in split:
            stripped = fragment.strip()
            if merged and _CITATION_ONLY.fullmatch(stripped):
                merged[-1] = f"{merged[-1]} {stripped}"
            else:
                merged.append(fragment)

        sentences = [s.strip() for s in merged if len(s.strip()) > 10]

        factual_sentences = 0
        cited_sentences = 0

        for sentence in sentences:
            # Skip headers, list markers, introductory phrases
            if sentence.startswith("#") or sentence.startswith("-") or sentence.startswith("*"):
                continue
            if sentence.endswith(":"):
                continue

            is_factual = bool(_FACTUAL_INDICATORS.search(sentence))
            has_citation = bool(CITATION_RE.search(sentence))

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
