"""Stage 4 (Thinking Mode): Adaptive Answer Synthesis.

Selects query-type-specific system prompts, runs a lightweight
think-then-answer planning step, then streams the final answer.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import structlog

from infrastructure.config import settings

if TYPE_CHECKING:
    from application.dtos.chat_dtos import ChatMessageDTO
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort
    from infrastructure.chat.models import ContextMetadata, QueryPlan

log = structlog.get_logger(__name__)

# Map query_type → system prompt key
_SYSTEM_PROMPT_MAP = {
    "factual": "chat_system_factual",
    "comparative": "chat_system_comparative",
    "exploratory": "chat_system_exploratory",
    "compound": "chat_system_compound",
    "follow_up": "chat_system_followup",
}


class AdaptiveSynthesisNode:
    """Generate a grounded answer with query-type-specific prompting."""

    def __init__(
        self,
        llm_client: LLMClientPort,
        prompt_repository: PromptRepositoryPort,
    ) -> None:
        self._llm = llm_client
        self._prompts = prompt_repository

    async def run(
        self,
        question: str,
        plan: QueryPlan,
        sources_text: str,
        context_meta: ContextMetadata,
        conversation_history: list[ChatMessageDTO],
    ) -> AsyncGenerator[str, None]:
        """Stream answer tokens with adaptive prompting."""
        _debug = settings.chat_debug
        conversation_context = _format_history(conversation_history)

        # Select query-type-specific system prompt
        system_key = _SYSTEM_PROMPT_MAP.get(plan.query_type, "chat_system_factual")
        try:
            system_prompt = await self._prompts.render_prompt(system_key)
        except Exception:
            log.warning(
                "chat.adaptive_synthesis.system_prompt_fallback",
                attempted=system_key,
            )
            system_prompt = await self._prompts.render_prompt(
                "chat_system", workspace_context="",
            )

        # Build context hints from metadata
        context_hints = self._build_context_hints(context_meta, plan)

        # Think-then-answer planning step (small non-streaming call)
        answer_plan = await self._plan_answer(
            question, plan, sources_text, context_hints,
        )

        if _debug:
            log.info(
                "chat.debug.adaptive_synthesis.plan",
                system_key=system_key,
                context_hints=context_hints,
                answer_plan_len=len(answer_plan),
                answer_plan_preview=answer_plan[:300],
            )

        # Build synthesis prompt
        user_prompt = await self._prompts.render_prompt(
            "chat_answer_synthesis_v2",
            question=question,
            sources=sources_text,
            conversation_context=conversation_context or "No prior conversation.",
            analysis_summary=plan.summary,
            answer_plan=answer_plan,
            context_hints=context_hints,
        )

        if _debug:
            log.info(
                "chat.debug.adaptive_synthesis.prompt",
                system_len=len(system_prompt),
                user_prompt_len=len(user_prompt),
            )

        token_count = 0
        async for token in self._llm.stream(
            user_prompt,
            system_prompt=system_prompt,
        ):
            token_count += 1
            yield token

        if _debug:
            log.info("chat.debug.adaptive_synthesis.done", tokens=token_count)

    async def _plan_answer(
        self,
        question: str,
        plan: QueryPlan,
        sources_text: str,
        context_hints: str,
    ) -> str:
        """Small non-streaming LLM call to plan the answer structure."""
        try:
            prompt = await self._prompts.render_prompt(
                "chat_answer_plan",
                question=question,
                query_type=plan.query_type,
                sources_preview=sources_text[:3000],
                context_hints=context_hints,
            )
            raw = await self._llm.complete(prompt)
            return raw.strip()[:500]  # Cap planning output
        except Exception as exc:
            log.warning("chat.adaptive_synthesis.plan_failed", error=str(exc))
            return "Answer the question directly using the provided sources."

    def _build_context_hints(
        self,
        meta: ContextMetadata,
        plan: QueryPlan,
    ) -> str:
        """Build context-aware hints for the synthesis prompt."""
        hints = []

        if meta.unique_artifacts == 1:
            hints.append("All sources come from a single document.")
        elif meta.unique_artifacts > 5:
            hints.append(f"Sources span {meta.unique_artifacts} different documents — synthesize across them.")

        if meta.avg_relevance_score < 0.4:
            hints.append("Sources may have limited relevance — be conservative and acknowledge gaps.")

        if meta.has_summaries:
            hints.append("Some sources are document summaries. Use summaries for context, cite chunks for factual claims.")

        if meta.high_relevance_count == 0:
            hints.append("No highly relevant sources found. Be explicit about uncertainty.")

        if plan.sub_queries:
            hints.append(f"The question was decomposed into {len(plan.sub_queries)} sub-queries. Address each aspect.")

        return " ".join(hints) if hints else "Standard context — proceed normally."


def _format_history(history: list[ChatMessageDTO]) -> str:
    if not history:
        return ""
    lines = []
    for msg in history[-6:]:
        role = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{role}: {msg.content[:500]}")
    return "\n".join(lines)
