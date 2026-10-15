"""Self-serve: the workspace scope picks the embedding model; no scope is an error."""

from __future__ import annotations

import pytest

from application.services.embedding_models import EmbeddingSpec
from infrastructure.embeddings.api_embedding_generator import ApiEmbeddingGenerator
from infrastructure.embeddings.scoped_embedding_generator import ScopedEmbeddingGenerator
from infrastructure.llm import llm_context


class Server:
    async def generate_text_embedding(self, text, model_name=None):
        return "server"

    async def get_model_info(self):
        return {"model_name": "local"}


async def test_unscoped_call_raises_instead_of_guessing() -> None:
    with pytest.raises(RuntimeError, match="outside a workspace scope"):
        await ScopedEmbeddingGenerator(Server(), 768).generate_text_embedding("x")


async def test_none_means_server_model() -> None:
    token = llm_context.set_embedding_spec(None)
    try:
        assert await ScopedEmbeddingGenerator(Server(), 768).generate_text_embedding("x") == "server"
    finally:
        llm_context.reset_embedding_spec(token)


def test_spec_routes_to_a_cached_api_generator() -> None:
    gen = ScopedEmbeddingGenerator(Server(), 768)
    spec = EmbeddingSpec(model="m", sdk="openai", provider_model="m", api_key="k")
    token = llm_context.set_embedding_spec(spec)
    try:
        first = gen._target()
        assert isinstance(first, ApiEmbeddingGenerator)
        assert gen._target() is first
    finally:
        llm_context.reset_embedding_spec(token)


async def test_model_info_reports_the_server_model() -> None:
    assert await ScopedEmbeddingGenerator(Server(), 768).get_model_info() == {"model_name": "local"}


def test_nomic_gets_its_trained_prefixes_unless_configured() -> None:
    from infrastructure.embeddings.sentence_transformer_generator import (
        SentenceTransformerGenerator,
    )

    nomic = SentenceTransformerGenerator(model_name="nomic-ai/nomic-embed-text-v1.5")
    assert (nomic.query_prefix, nomic.document_prefix) == ("search_query: ", "search_document: ")
    custom = SentenceTransformerGenerator(
        model_name="nomic-ai/nomic-embed-text-v1.5", query_prefix="q: ", document_prefix="d: "
    )
    assert (custom.query_prefix, custom.document_prefix) == ("q: ", "d: ")
    granite = SentenceTransformerGenerator(model_name="ibm-granite/granite-embedding-english-r2")
    assert (granite.query_prefix, granite.document_prefix) == ("", "")
