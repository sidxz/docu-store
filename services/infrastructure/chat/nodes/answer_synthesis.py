"""Step 3: Generate a grounded answer with streaming and inline citations."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import structlog

from infrastructure.config import settings

if TYPE_CHECKING:
    from application.dtos.chat_dtos import ChatMessageDTO, SourceCitationDTO
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort
    from infrastructure.chat.models import QuestionAnalysis

log = structlog.get_logger(__name__)


class AnswerSynthesisNode:
    """Generate a grounded answer from sources, streaming tokens."""

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
        analysis: QuestionAnalysis,
        sources_text: str,
        conversation_history: list[ChatMessageDTO],
    ) -> AsyncGenerator[str, None]:
        """Stream answer tokens."""
        conversation_context = _format_history(conversation_history)

        system_prompt = await self._prompts.render_prompt(
            "chat_system",
            workspace_context="",
        )

        user_prompt = await self._prompts.render_prompt(
            "chat_answer_synthesis",
            question=question,
            sources=sources_text,
            conversation_context=conversation_context or "No prior conversation.",
            analysis_summary=analysis.summary,
        )

        log.debug(
            "chat.synthesis.start",
            prompt_len=len(user_prompt),
            system_len=len(system_prompt),
        )

        if settings.chat_debug:
            log.info(
                "chat.debug.synthesis.prompts",
                system_prompt_preview=system_prompt[:300],
                user_prompt_len=len(user_prompt),
                user_prompt_preview=user_prompt[:500],
                sources_text_len=len(sources_text),
                conversation_context_len=len(conversation_context),
            )

        token_count = 0
        async for token in self._llm.stream(
            user_prompt,
            system_prompt=system_prompt,
        ):
            token_count += 1
            yield token

        if settings.chat_debug:
            log.info("chat.debug.synthesis.done", tokens_streamed=token_count)


def _format_history(history: list[ChatMessageDTO]) -> str:
    if not history:
        return ""
    lines = []
    for msg in history[-6:]:
        role = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{role}: {msg.content[:500]}")
    return "\n".join(lines)
