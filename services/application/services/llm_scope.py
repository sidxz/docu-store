"""Resolve the caller's per-user LLM config into the current context.

Resolution order (spec Phase 2): user config (flag on) → env defaults →
``LLMNotConfiguredError`` — the last two happen inside the adapters. This scope
only decides *which* ``UserLLMConfig`` (or None) the adapters see, and for how
long. Precedent: ``ingestion_counter(artifact)`` sets the token-usage scope the
same way at the same call sites.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, asynccontextmanager, nullcontext
from typing import TYPE_CHECKING

from infrastructure.llm import llm_context

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from application.ports.user_llm_config import UserLLMConfig, UserLLMConfigStore
    from domain.aggregates.artifact import Artifact


class UserLLMScope:
    def __init__(self, store: UserLLMConfigStore, *, enabled: bool) -> None:
        self._store = store
        self._enabled = enabled

    @asynccontextmanager
    async def for_user(
        self,
        workspace_id: UUID | None,
        user_id: UUID | None,
    ) -> AsyncIterator[UserLLMConfig | None]:
        config = None
        if self._enabled and workspace_id is not None and user_id is not None:
            config = await self._store.get(workspace_id, user_id)
        token = llm_context.set_user_config(config)
        try:
            yield config
        finally:
            try:  # noqa: SIM105 — explicit except keeps the teardown comment attached
                llm_context.reset_user_config(token)
            except ValueError:
                # Exit ran in another Context (framework teardown); that
                # context is gone with the request, so nothing leaks.
                pass

    def for_owner(self, artifact: Artifact) -> AbstractAsyncContextManager[UserLLMConfig | None]:
        """The uploader's config — Artifact carries workspace_id/owner_id at every enrichment site."""
        return self.for_user(artifact.workspace_id, artifact.owner_id)


def owner_scope(
    scope: UserLLMScope | None,
    artifact: Artifact,
) -> AbstractAsyncContextManager[UserLLMConfig | None]:
    """``scope.for_owner(artifact)``, or a no-op when the use case has no scope (tests)."""
    return scope.for_owner(artifact) if scope is not None else nullcontext()
