"""Resolve a workspace's BYO LLM config into the current context.

Resolution order (spec Phase 2): workspace config (flag on) → env defaults →
``LLMNotConfiguredError`` — the last two happen inside the adapters. This scope
only decides *which* ``UserLLMConfig`` (or None) the adapters see, and for how
long. Precedent: ``ingestion_counter(artifact)`` sets the token-usage scope the
same way at the same call sites.

With a workspace embedding store (self-serve) the scope also resolves which
embedding model the workspace uses and which of its keys serves it — into a
second contextvar read by ``ScopedEmbeddingGenerator``.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, asynccontextmanager, nullcontext
from typing import TYPE_CHECKING

from application.services.embedding_models import (
    EMBEDDING_MODELS,
    LOCAL_EMBEDDING_MODEL,
    EmbeddingSpec,
    missing_key_spec,
    spec_for_provider,
)
from infrastructure.llm import llm_context

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from application.ports.user_llm_config import UserLLMConfig, UserLLMConfigStore
    from application.ports.workspace_embedding_config import WorkspaceEmbeddingConfigStore
    from domain.aggregates.artifact import Artifact
    from domain.aggregates.page import Page


class UserLLMScope:
    def __init__(
        self,
        store: UserLLMConfigStore,
        *,
        enabled: bool,
        embedding_store: WorkspaceEmbeddingConfigStore | None = None,
    ) -> None:
        self._store = store
        self._enabled = enabled
        self._embedding_store = embedding_store

    async def embedding_spec(self, workspace_id: UUID | None) -> EmbeddingSpec | None:
        """The workspace's API embedding model through one of its keys.

        None = the server model. A spec without a key (``missing_key_message``)
        fails closed at the call — never a fallback to the server model, whose
        vectors would land in a different space.
        """
        if self._embedding_store is None or workspace_id is None:
            return None
        config = await self._embedding_store.get(workspace_id)
        if config is None:
            return None
        return await self.spec_for_model(config.model, workspace_id)

    async def spec_for_model(self, model: str, workspace_id: UUID) -> EmbeddingSpec | None:
        """``model`` through the workspace's keys (also used to vet a model before saving it)."""
        if model == LOCAL_EMBEDDING_MODEL:
            return None
        preset = EMBEDDING_MODELS.get(model)
        if preset is None:
            return missing_key_spec(model)
        # The active provider first, so switching providers steers billing.
        active = await self._store.get_entry(workspace_id)
        order = sorted(preset.providers, key=lambda p: active is None or p != active.provider)
        for provider in order:
            config = await self._store.get_config(workspace_id, provider)
            if config is not None and config.api_key:
                return spec_for_provider(model, provider, config.api_key)
        return missing_key_spec(model)

    @asynccontextmanager
    async def for_workspace(self, workspace_id: UUID | None) -> AsyncIterator[UserLLMConfig | None]:
        config = None
        if self._enabled and workspace_id is not None:
            config = await self._store.get(workspace_id)
        embedding = await self.embedding_spec(workspace_id)
        token = llm_context.set_user_config(config)
        embedding_token = llm_context.set_embedding_spec(embedding)
        try:
            yield config
        finally:
            try:
                llm_context.reset_embedding_spec(embedding_token)
                llm_context.reset_user_config(token)
            except ValueError:
                # Exit ran in another Context (framework teardown); that
                # context is gone with the request, so nothing leaks.
                pass


def workspace_scope(
    scope: UserLLMScope | None,
    aggregate: Artifact | Page,
) -> AbstractAsyncContextManager[UserLLMConfig | None]:
    """The aggregate's workspace config, or a no-op when the use case has no scope (tests)."""
    return scope.for_workspace(aggregate.workspace_id) if scope is not None else nullcontext()
