from __future__ import annotations

import asyncio
from uuid import uuid4

from application.ports.user_llm_config import NullUserLLMConfigStore, UserLLMConfig
from domain.exceptions import (
    InfrastructureError,
    LLMAuthError,
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitedError,
)
from infrastructure.llm.llm_context import get_user_config, reset_user_config, set_user_config

CFG = UserLLMConfig(provider="openai", api_key="sk-secret", base_url="https://openrouter.ai/api/v1")


def test_taxonomy_shape() -> None:
    assert issubclass(LLMError, InfrastructureError)
    assert LLMNotConfiguredError("x").retryable is False
    assert LLMAuthError("x").retryable is False
    assert LLMRateLimitedError("x").retryable is True


def test_api_key_never_in_repr() -> None:
    assert "sk-secret" not in repr(CFG)


def test_set_get_reset() -> None:
    assert get_user_config() is None
    tok = set_user_config(CFG)
    try:
        assert get_user_config() is CFG
    finally:
        reset_user_config(tok)
    assert get_user_config() is None


async def test_propagates_into_task_created_inside_scope() -> None:
    # ChatRunRegistry.start() → asyncio.create_task copies the context at creation.
    async def read() -> UserLLMConfig | None:
        return get_user_config()

    tok = set_user_config(CFG)
    try:
        task = asyncio.create_task(read())
    finally:
        reset_user_config(tok)
    assert await task is CFG


async def test_null_store_returns_none() -> None:
    assert await NullUserLLMConfigStore().get(uuid4(), uuid4()) is None
