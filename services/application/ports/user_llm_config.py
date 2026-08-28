"""Per-user LLM provider configuration (BYO key).

A user may keep one entry per provider and one of them is *active* — the config
every ingestion, chat and NER call resolves to. Switching is therefore additive:
connecting a second provider never destroys the credential of the first, so a
provider that turns out not to work costs one click to back out of rather than
a key you may no longer have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime
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
    active: bool = False
    updated_at: datetime | None = None


class UserLLMConfigStore(Protocol):
    async def get(self, workspace_id: UUID, user_id: UUID) -> UserLLMConfig | None:
        """Resolver path: the *active* config, decrypted, with the effective provider/base_url."""
        ...

    async def get_config(
        self,
        workspace_id: UUID,
        user_id: UUID,
        provider: str,
    ) -> UserLLMConfig | None:
        """One stored provider, active or not — so the UI can test before switching."""
        ...

    async def get_entry(self, workspace_id: UUID, user_id: UUID) -> UserLLMProviderEntry | None:
        """The active entry, or None when nothing is active — i.e. "has a usable LLM"."""
        ...

    async def list_entries(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> list[UserLLMProviderEntry]:
        """Everything the caller has configured, newest first."""
        ...

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
        """Upsert this provider's entry and make it the active one. Others are kept."""
        ...

    async def update_models(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        provider: str,
        model: str,
        chat_model: str,
    ) -> bool:
        """Change one entry's lane models, keeping its key. False when it does not exist."""
        ...

    async def activate(self, workspace_id: UUID, user_id: UUID, provider: str) -> bool:
        """Make a stored provider the active one. False when it does not exist."""
        ...

    async def delete(self, workspace_id: UUID, user_id: UUID, provider: str) -> bool:
        """Forget one provider. Deleting the active one leaves nothing active."""
        ...

    async def ensure_indexes(self) -> None: ...


class NullUserLLMConfigStore:
    """No per-user config anywhere (today's deployments)."""

    async def get(self, workspace_id: UUID, user_id: UUID) -> UserLLMConfig | None:
        return None

    async def get_config(
        self,
        workspace_id: UUID,
        user_id: UUID,
        provider: str,
    ) -> UserLLMConfig | None:
        return None

    async def get_entry(self, workspace_id: UUID, user_id: UUID) -> UserLLMProviderEntry | None:
        return None

    async def list_entries(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> list[UserLLMProviderEntry]:
        return []

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
        provider: str,
        model: str,
        chat_model: str,
    ) -> bool:
        return False

    async def activate(self, workspace_id: UUID, user_id: UUID, provider: str) -> bool:
        return False

    async def delete(self, workspace_id: UUID, user_id: UUID, provider: str) -> bool:
        return False

    async def ensure_indexes(self) -> None:
        return None
