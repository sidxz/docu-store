"""Request/activity-scoped per-user LLM config (set by UserLLMScope, read by the
LLM adapters via ``effective_spec``). Sibling of ``reasoning_context`` — same
contextvar shape, different setter and lifetime.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.user_llm_config import UserLLMConfig

_user_config: ContextVar[UserLLMConfig | None] = ContextVar("user_llm_config", default=None)


def set_user_config(config: UserLLMConfig | None) -> Token:
    return _user_config.set(config)


def reset_user_config(token: Token) -> None:
    _user_config.reset(token)


def get_user_config() -> UserLLMConfig | None:
    return _user_config.get()
