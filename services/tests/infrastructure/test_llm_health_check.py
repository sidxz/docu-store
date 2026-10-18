"""In self-serve the LLM health check reports the workspace's provider, not LLM_API_KEY."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from application.ports.user_llm_config import UserLLMProviderEntry
from infrastructure.health.health_checker import InfrastructureHealthChecker


class Store:
    def __init__(self, entry: UserLLMProviderEntry | None) -> None:
        self.entry = entry

    async def get_entry(self, workspace_id):
        return self.entry


def _checker(entry: UserLLMProviderEntry | None) -> InfrastructureHealthChecker:
    return InfrastructureHealthChecker(
        mongo_client=None, vector_store=None, compound_vector_store=None,
        summary_vector_store=None, embedding_generator=None, chemberta_generator=None,
        reranker=None, heartbeat_store=None,
        settings=SimpleNamespace(user_llm_keys_enabled=True, llm_provider="openai", llm_api_key=None),
        llm_store=Store(entry),
    )


async def test_workspace_provider_is_healthy_without_a_server_key() -> None:
    entry = UserLLMProviderEntry(provider="openai", model="m", chat_model="c", key_last4="6_kA", active=True)
    status = await _checker(entry)._check_llm(uuid4())
    assert status.status == "healthy"
    assert status.details["configured_model"] == "m"


async def test_workspace_without_a_provider_is_degraded() -> None:
    status = await _checker(None)._check_llm(uuid4())
    assert status.status == "degraded"
    assert "Settings → AI Provider" in status.error
