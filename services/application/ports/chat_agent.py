"""Port for the agentic RAG chat pipeline."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Protocol
from uuid import UUID

from application.dtos.chat_dtos import AgentEvent, ChatMessageDTO


class ChatAgentPort(Protocol):
    """Runs the multi-step agent pipeline and yields streaming events.

    The agent flow: Question Analysis -> Retrieval -> Synthesis -> Grounding Verification
    with a conditional retry loop if grounding fails.
    """

    async def run(
        self,
        message: str,
        conversation_history: list[ChatMessageDTO],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]: ...
