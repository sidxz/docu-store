"""Per-user LLM provider configuration (BYO key).

Phase 2 defined the shape and the port; Phase 3 grows the port for the settings API and registers the Mongo store in the container when USER_LLM_KEYS_ENABLED is on.
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


@dataclass(frozen=True)
class UserLLMProviderEntry:
    """What the settings UI may see — never the key."""

    provider: str  # user-facing id: openrouter | openai | gemini
    model: str
    chat_model: str
    key_last4: str


class UserLLMConfigStore(Protocol):
    async def get(self, workspace_id: UUID, user_id: UUID) -> UserLLMConfig | None:
        """Resolver path: decrypted config with the *effective* provider/base_url."""
        ...

    async def get_entry(self, workspace_id: UUID, user_id: UUID) -> UserLLMProviderEntry | None: ...

    async def set(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        provider: str,
        api_key: str,
        model: str,
        chat_model: str,
    ) -> None:
        """Upsert the caller's row (one per (workspace, user))."""
        ...

    async def update_models(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        model: str,
        chat_model: str,
    ) -> bool:
        """Change lane models without re-entering the key. False when no row exists."""
        ...

    async def delete(self, workspace_id: UUID, user_id: UUID) -> None: ...

    async def ensure_indexes(self) -> None: ...


class NullUserLLMConfigStore:
    """No per-user config anywhere (today's deployments)."""

    async def get(self, workspace_id: UUID, user_id: UUID) -> UserLLMConfig | None:
        return None

    async def get_entry(self, workspace_id: UUID, user_id: UUID) -> UserLLMProviderEntry | None:
        return None

    async def set(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        provider: str,
        api_key: str,
        model: str,
        chat_model: str,
    ) -> None:
        msg = "Per-user LLM keys are off (USER_LLM_KEYS_ENABLED=false)."
        raise RuntimeError(msg)

    async def update_models(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        model: str,
        chat_model: str,
    ) -> bool:
        return False

    async def delete(self, workspace_id: UUID, user_id: UUID) -> None:
        return None

    async def ensure_indexes(self) -> None:
        return None
