"""Build conversation context for the LLM with sliding window + summary."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.chat_dtos import ChatMessageDTO
    from application.ports.chat_repository import ChatRepository
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort

log = structlog.get_logger(__name__)

# Threshold: if conversation has more messages than this, generate a summary
_SUMMARY_THRESHOLD = 12


class ContextBuilder:
    """Manage conversation context with a sliding window and LLM-generated summary."""

    def __init__(
        self,
        chat_repository: ChatRepository,
        llm_client: LLMClientPort,
        prompt_repository: PromptRepositoryPort,
        max_recent_messages: int = 10,
    ) -> None:
        self._repo = chat_repository
        self._llm = llm_client
        self._prompts = prompt_repository
        self._max_recent = max_recent_messages

    async def get_context_messages(
        self,
        conversation_id: UUID,
    ) -> list[ChatMessageDTO]:
        """Get the most recent messages for the context window."""
        return await self._repo.get_recent_messages(
            conversation_id,
            limit=self._max_recent,
        )

    async def maybe_update_summary(
        self,
        conversation_id: UUID,
        messages: list[ChatMessageDTO],
    ) -> None:
        """If the conversation is long enough, generate/update a summary of older messages."""
        total = len(messages)
        if total < _SUMMARY_THRESHOLD:
            return

        # Summarize the older messages (everything except the last few)
        older = messages[: total - self._max_recent]
        if not older:
            return

        conversation_text = "\n".join(
            f"{'User' if m.role == 'user' else 'Assistant'}: {m.content[:300]}"
            for m in older
        )

        prompt = await self._prompts.render_prompt(
            "chat_conversation_summary",
            conversation_text=conversation_text,
        )

        summary = await self._llm.complete(prompt)

        await self._repo.save_conversation_summary(conversation_id, summary)
        log.debug("chat.context.summary_updated", conversation_id=str(conversation_id))
