"""Request/activity-scoped per-user LLM config (set by UserLLMScope, read by the
LLM adapters via ``effective_spec``). Sibling of ``reasoning_context`` — same
contextvar shape, different setter and lifetime.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.user_llm_config import UserLLMConfig
    from application.services.embedding_models import EmbeddingSpec

_user_config: ContextVar[UserLLMConfig | None] = ContextVar("user_llm_config", default=None)


def set_user_config(config: UserLLMConfig | None) -> Token:
    return _user_config.set(config)


def reset_user_config(token: Token) -> None:
    _user_config.reset(token)


def get_user_config() -> UserLLMConfig | None:
    return _user_config.get()


# Workspace embedding model (self-serve): set by the same scope, read by
# ScopedEmbeddingGenerator. NOT_SCOPED means no scope ran at all — a call site
# that would otherwise embed with the server model while the workspace's
# vectors live in another model's space.
NOT_SCOPED = object()
_embedding_spec: ContextVar[EmbeddingSpec | None | object] = ContextVar(
    "workspace_embedding_spec", default=NOT_SCOPED
)


def set_embedding_spec(spec: EmbeddingSpec | None) -> Token:
    return _embedding_spec.set(spec)


def reset_embedding_spec(token: Token) -> None:
    _embedding_spec.reset(token)


def get_embedding_spec() -> EmbeddingSpec | None | object:
    return _embedding_spec.get()
