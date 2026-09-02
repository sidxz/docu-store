"""Router that dispatches to Quick, Thinking, Deep Thinking or Literature chat agent."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Literal
from uuid import UUID

from application.dtos.chat_dtos import AgentEvent, ChatMessageDTO, SourceCitationDTO
from application.ports.chat_agent import ChatAgentPort


class ChatAgentRouter:
    """Routes to Quick, Thinking, or Deep Thinking agent based on mode selection."""

    def __init__(
        self,
        quick_agent: ChatAgentPort,
        thinking_agent: ChatAgentPort,
        deep_thinking_agent: ChatAgentPort,
        literature_agent: ChatAgentPort | None = None,
        default_mode: Literal["quick", "thinking", "deep_thinking"] = "thinking",
    ) -> None:
        self._quick = quick_agent
        self._thinking = thinking_agent
        self._deep_thinking = deep_thinking_agent
        self._literature = literature_agent
        self._default_mode = default_mode

    async def run(
        self,
        message: str,
        conversation_history: list[ChatMessageDTO],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None = None,
        mode: Literal["quick", "thinking", "deep_thinking", "literature"] | None = None,
        previous_citations: list[SourceCitationDTO] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        effective_mode = mode or self._default_mode
        if effective_mode == "literature":
            if self._literature is None:
                # Never silently answer a literature question from the corpus:
                # the two surfaces mean different things by a source.
                msg = "Literature mode is not enabled on this deployment"
                raise ValueError(msg)
            agent = self._literature
        elif effective_mode == "deep_thinking":
            agent = self._deep_thinking
        elif effective_mode == "thinking":
            agent = self._thinking
        else:
            agent = self._quick

        async for event in agent.run(
            message=message,
            conversation_history=conversation_history,
            workspace_id=workspace_id,
            allowed_artifact_ids=allowed_artifact_ids,
            previous_citations=previous_citations,
        ):
            yield event
