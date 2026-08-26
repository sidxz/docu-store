"""USER_LLM_KEYS_ENABLED wiring: Null store off, Mongo store on, boot failure without a secret."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from application.ports.user_llm_config import NullUserLLMConfigStore, UserLLMConfigStore
from infrastructure.config import Settings
from infrastructure.di import container as container_module
from infrastructure.read_repositories.mongo_user_llm_provider_store import (
    MongoUserLLMProviderStore,
)


def test_settings_are_resolvable_from_the_container(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(container_module.settings, "user_llm_keys_enabled", False)
    c = container_module.create_container()
    assert c[Settings] is container_module.settings


def test_flag_off_keeps_null_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(container_module.settings, "user_llm_keys_enabled", False)
    monkeypatch.setattr(container_module.settings, "user_llm_keys_secret", None)
    c = container_module.create_container()
    assert isinstance(c[UserLLMConfigStore], NullUserLLMConfigStore)


def test_flag_on_without_secret_fails_at_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(container_module.settings, "user_llm_keys_enabled", True)
    monkeypatch.setattr(container_module.settings, "user_llm_keys_secret", None)
    with pytest.raises(ValueError, match="USER_LLM_KEYS_SECRET"):
        container_module.create_container()


async def test_flag_on_with_secret_wires_mongo_store(monkeypatch: pytest.MonkeyPatch) -> None:
    # async: Motor clients are cached per running loop in the container factory
    monkeypatch.setattr(container_module.settings, "user_llm_keys_enabled", True)
    monkeypatch.setattr(
        container_module.settings, "user_llm_keys_secret", Fernet.generate_key().decode(),
    )
    c = container_module.create_container()
    assert isinstance(c[UserLLMConfigStore], MongoUserLLMProviderStore)
