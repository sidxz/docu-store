"""server_llm_available: can the env defaults serve an LLM call?"""

from __future__ import annotations

from types import SimpleNamespace

from infrastructure.llm.factory import server_llm_available


def _s(provider: str, **keys: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        llm_provider=provider,
        openai_api_key=keys.get("openai"),
        anthropic_api_key=keys.get("anthropic"),
        google_api_key=keys.get("google"),
        llm_api_key=keys.get("generic"),
    )


def test_local_provider_needs_no_key() -> None:
    assert server_llm_available(_s("ollama")) is True


def test_cloud_provider_without_any_key_is_unavailable() -> None:
    assert server_llm_available(_s("openai")) is False


def test_cloud_provider_with_specific_or_generic_key() -> None:
    assert server_llm_available(_s("openai", openai="k")) is True
    assert server_llm_available(_s("gemini", generic="k")) is True
