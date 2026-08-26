"""Per-user LLM provider configuration (BYO key).

Phase 2 defines the shape and the port; the Mongo-backed store (Phase 3)
replaces ``NullUserLLMConfigStore`` in the container.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID


@dataclass(frozen=True)
class UserLLMConfig:
    provider: str  # openai | anthropic | gemini | ollama
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None  # e.g. https://openrouter.ai/api/v1
    model: str | None = None  # batch + NER lanes; None → env model
    chat_model: str | None = None  # chat lanes; None → model → env model


class UserLLMConfigStore(Protocol):
    async def get(self, workspace_id: UUID, user_id: UUID) -> UserLLMConfig | None: ...


class NullUserLLMConfigStore:
    """No per-user config anywhere (today's deployments)."""

    async def get(self, workspace_id: UUID, user_id: UUID) -> UserLLMConfig | None:
        return None
