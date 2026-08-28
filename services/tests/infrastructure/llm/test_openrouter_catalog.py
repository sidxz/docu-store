"""OpenRouter's published capabilities: cached, fail-open, and a reliable no only."""

from __future__ import annotations

import pytest

from infrastructure.llm import openrouter_catalog


@pytest.fixture(autouse=True)
def _cold_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(openrouter_catalog, "_cache", None)
    monkeypatch.setattr(openrouter_catalog, "_cached_at", 0.0)


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, catalog, *, fail: bool = False) -> list[int]:
    calls: list[int] = []

    async def fake():
        calls.append(1)
        return None if fail else {k: frozenset(v) for k, v in catalog.items()}

    monkeypatch.setattr(openrouter_catalog, "_fetch_catalog", fake)
    return calls


async def test_a_listed_capability_is_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fetch(monkeypatch, {"openai/gpt-5-mini": ["response_format", "structured_outputs"]})

    assert await openrouter_catalog.supports_structured_outputs("openai/gpt-5-mini") is True


async def test_response_format_without_structured_outputs_is_no(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 22% that answer a probe in prose instead of refusing it."""
    _patch_fetch(monkeypatch, {"z-ai/glm-5.3": ["response_format"]})

    assert await openrouter_catalog.supports_structured_outputs("z-ai/glm-5.3") is False


async def test_an_unlisted_model_is_unknown_not_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetch(monkeypatch, {"openai/gpt-5-mini": ["structured_outputs"]})

    assert await openrouter_catalog.supports_structured_outputs("some/private-model") is None


async def test_an_unreachable_catalog_is_unknown_not_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A third-party outage must never become a verdict about a model."""
    _patch_fetch(monkeypatch, {}, fail=True)

    assert await openrouter_catalog.supports_structured_outputs("openai/gpt-5-mini") is None


async def test_the_catalog_is_fetched_once_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_fetch(monkeypatch, {"a/b": ["structured_outputs"], "c/d": []})

    assert await openrouter_catalog.supports_structured_outputs("a/b") is True
    assert await openrouter_catalog.supports_structured_outputs("c/d") is False
    assert len(calls) == 1


async def test_a_failed_refresh_keeps_serving_the_last_good_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetch(monkeypatch, {"a/b": ["structured_outputs"]})
    assert await openrouter_catalog.supports_structured_outputs("a/b") is True

    monkeypatch.setattr(openrouter_catalog, "_cached_at", 0.0)  # expire it
    _patch_fetch(monkeypatch, {}, fail=True)

    assert await openrouter_catalog.supports_structured_outputs("a/b") is True
