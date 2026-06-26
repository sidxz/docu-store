"""Stage 4 (Thinking Mode): Adaptive Answer Synthesis.

Selects query-type-specific system prompts, runs a lightweight
think-then-answer planning step, then streams the final answer.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Literal

import structlog

from application.dtos.chat_dtos import AgentEvent
from infrastructure.chat.utils import build_conversation_context
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
        images_b64: list[str] | None = None,
    ) -> AsyncGenerator[tuple[Literal["token", "event"], str | AgentEvent], None]:
        """Stream answer tokens with adaptive prompting.

        Yields tagged tuples: ("event", AgentEvent) for intermediate thinking
        content, ("token", str) for answer tokens.
        """
        _debug = settings.chat_debug
        conversation_context = build_conversation_context(conversation_history, max_chars=500)

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
                "chat_system",
                workspace_context="",
            )

        # Build context hints from metadata
        context_hints = self._build_context_hints(context_meta, plan)
        if images_b64:
            context_hints += (
                f" {len(images_b64)} page images are attached for visual context."
                " Reference figures, charts, or diagrams visible in the images when relevant."
            )

        # Think-then-answer planning step (small non-streaming call)
        answer_plan = await self._plan_answer(
            question,
            plan,
            sources_text,
            context_hints,
        )

        if _debug:
            log.info(
                "chat.debug.adaptive_synthesis.plan",
                system_key=system_key,
                context_hints=context_hints,
                answer_plan_len=len(answer_plan),
                answer_plan_preview=answer_plan[:300],
            )

        # Emit the answer plan as thinking content for the agent trace
        yield (
            "event",
            AgentEvent(
                type="step_completed",
                step="synthesis",
                status="started",
                output="Answer plan generated",
                thinking_content=answer_plan,
                thinking_label="Answer Planning",
            ),
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
        async for kind, text in self._llm.stream_with_reasoning(
            user_prompt,
            system_prompt=system_prompt,
            images_b64=images_b64,
        ):
            if kind == "reasoning":
                yield ("event", AgentEvent(type="reasoning_token", delta=text))
            else:
                token_count += 1
                yield ("token", text)

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
            hints.append(
                f"Sources span {meta.unique_artifacts} different documents — synthesize across them.",
            )

        if meta.avg_relevance_score < 0.4:
            hints.append(
                "Sources may have limited relevance — be conservative and acknowledge gaps.",
            )

        if meta.has_summaries:
            hints.append(
                "Some sources are document summaries. Use summaries for context, cite chunks for factual claims.",
            )

        if meta.high_relevance_count == 0:
            hints.append("No highly relevant sources found. Be explicit about uncertainty.")

        if plan.sub_queries:
            hints.append(
                f"The question was decomposed into {len(plan.sub_queries)} sub-queries. Address each aspect.",
            )

        return " ".join(hints) if hints else "Standard context — proceed normally."
