"""API embedding adapter: dimensions enforced, prefixes applied, failures typed."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.services.embedding_models import EmbeddingSpec
from application.services.llm_providers import OPENROUTER_BASE_URL
from domain.exceptions import LLMAuthError, LLMBadRequestError, LLMNotConfiguredError
from infrastructure.embeddings.api_embedding_generator import (
    ApiEmbeddingGenerator,
    env_embedding_spec,
)

DIMS = 4


class FakeOpenAI:
    def __init__(self, dims: int = DIMS, drop: int = 0, status: int | None = None) -> None:
        self.calls: list[dict] = []
        self.embeddings = self
        self._dims, self._drop, self._status = dims, drop, status

    async def create(self, *, model, input, dimensions):  # noqa: A002 -- SDK keyword
        self.calls.append({"model": model, "input": list(input), "dimensions": dimensions})
        if self._status:
            raise type("APIStatusError", (Exception,), {"status_code": self._status})("denied")
        data = [SimpleNamespace(index=i, embedding=[0.1] * self._dims) for i in range(len(input))]
        return SimpleNamespace(data=list(reversed(data))[self._drop :])


class FakeGemini:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.models = self

    async def embed_content(self, *, model, contents, config):
        self.calls.append({"model": model, "texts": [c.parts[0].text for c in contents],
                           "dims": config.output_dimensionality})
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.2] * DIMS) for _ in contents])


def _gen(client, *, sdk="openai", key="k", qp="", dp="", missing=None) -> ApiEmbeddingGenerator:
    spec = EmbeddingSpec(model="canon/m", sdk=sdk, provider_model="m", api_key=key,
                         query_prefix=qp, document_prefix=dp, missing_key_message=missing)
    gen = ApiEmbeddingGenerator(spec, DIMS)
    gen._client = client
    return gen


async def test_openai_batches_requests_dims_and_prefix() -> None:
    client = FakeOpenAI()
    out = await _gen(client, dp="doc: ").generate_batch_embeddings([f"t{i}" for i in range(130)])
    assert len(out) == 130
    assert [len(c["input"]) for c in client.calls] == [128, 2]
    assert all(c["dimensions"] == DIMS for c in client.calls)
    assert client.calls[0]["input"][0] == "doc: t0"
    assert out[0].model_name == "canon/m"


async def test_query_side_uses_query_prefix() -> None:
    client = FakeGemini()
    emb = await _gen(client, sdk="gemini", qp="task: search result | query: ").generate_text_embedding("aspirin")
    assert client.calls == [{"model": "m", "texts": ["task: search result | query: aspirin"], "dims": DIMS}]
    assert emb.dimensions == DIMS


async def test_wrong_dimension_or_count_is_rejected() -> None:
    with pytest.raises(LLMBadRequestError, match="dimensional"):
        await _gen(FakeOpenAI(dims=DIMS + 1)).generate_text_embedding("x")
    with pytest.raises(LLMBadRequestError, match="vectors for"):
        await _gen(FakeOpenAI(drop=1)).generate_batch_embeddings(["a", "b"])


async def test_missing_key_fails_closed_without_calling() -> None:
    client = FakeOpenAI()
    with pytest.raises(LLMNotConfiguredError, match="Connect"):
        await _gen(client, key=None, missing="Connect an OpenAI key").generate_text_embedding("x")
    assert client.calls == []


async def test_provider_auth_failure_is_typed() -> None:
    with pytest.raises(LLMAuthError):
        await _gen(FakeOpenAI(status=401)).generate_text_embedding("x")


def _settings(**kw):
    base = dict(embedding_model_provider="openai", embedding_model_name="text-embedding-3-small",
                embedding_api_key=None, embedding_base_url=None, openai_api_key=None,
                google_api_key=None, embedding_query_prefix="", embedding_document_prefix="")
    return SimpleNamespace(**{**base, **kw})


def test_env_spec_key_fallback_and_base_urls() -> None:
    spec = env_embedding_spec(_settings(openai_api_key="sk", embedding_base_url="https://foundry/v1"))
    assert (spec.api_key, spec.base_url, spec.missing_key_message) == ("sk", "https://foundry/v1", None)
    spec = env_embedding_spec(_settings(embedding_model_provider="openrouter",
                                        embedding_model_name="openai/text-embedding-3-small"))
    assert spec.base_url == OPENROUTER_BASE_URL
    assert "EMBEDDING_API_KEY" in spec.missing_key_message


def test_env_spec_known_gemini_model_brings_prefixes() -> None:
    spec = env_embedding_spec(_settings(embedding_model_provider="gemini",
                                        embedding_model_name="gemini-embedding-2",
                                        google_api_key="g"))
    assert spec.sdk == "gemini"
    assert spec.query_prefix.startswith("task: search result")
    assert spec.document_prefix.startswith("title: none")
