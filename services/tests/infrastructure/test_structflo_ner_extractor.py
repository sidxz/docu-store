"""Provider wiring for the StructfloNERExtractor adapter.

The adapter must forward provider/api_key/model_url to the structflo library
and degrade to dictionary-only NER when the provider is one langextract can't
route (anthropic/azure).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infrastructure.ner.structflo_ner_extractor import StructfloNERExtractor


@pytest.fixture
def stub_structflo(monkeypatch):
    """Patch the structflo library symbols the adapter imports at init time."""
    fake_ner_cls = MagicMock(name="NERExtractor")
    monkeypatch.setattr("structflo.ner.NERExtractor", fake_ner_cls)
    monkeypatch.setattr("structflo.ner.fast.FastNERExtractor", MagicMock())
    monkeypatch.setattr("structflo.ner.TB", object())
    return fake_ner_cls


def test_ollama_forwards_model_url(stub_structflo):
    StructfloNERExtractor(
        model_id="medgemma:latest", provider="ollama", model_url="http://ollama:11434"
    )
    _, kwargs = stub_structflo.call_args
    assert kwargs["provider"] == "ollama"
    assert kwargs["model_url"] == "http://ollama:11434"


def test_cloud_provider_passes_api_key_and_drops_model_url(stub_structflo):
    StructfloNERExtractor(
        model_id="gpt-4o", provider="openai", api_key="sk-x", model_url="http://ollama:11434"
    )
    _, kwargs = stub_structflo.call_args
    assert kwargs["provider"] == "openai"
    assert kwargs["api_key"] == "sk-x"
    # Cloud providers must not receive the Ollama base URL.
    assert kwargs["model_url"] is None


def test_unsupported_provider_degrades_to_fast_only(stub_structflo):
    extractor = StructfloNERExtractor(model_id="claude-x", provider="anthropic")
    # structflo LLM extractor is never constructed for an unroutable provider.
    stub_structflo.assert_not_called()
    assert extractor._llm_extractor is None
