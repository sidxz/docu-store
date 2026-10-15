"""Text embeddings from a hosted API: OpenAI-compatible (OpenAI, OpenRouter, any
``/v1/embeddings`` endpoint) or Gemini.

Same split as the local model: ``generate_text_embedding`` is the query side,
``generate_batch_embeddings`` the document side. Every call asks for the
configured dimension count and checks what comes back, so a provider that
ignores the parameter fails loudly instead of writing vectors Qdrant rejects —
or worse, accepts into the wrong space.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog

from application.services.embedding_models import EMBEDDING_MODELS, EmbeddingSpec
from application.services.llm_providers import OPENROUTER_BASE_URL
from domain.exceptions import LLMBadRequestError, LLMNotConfiguredError
from domain.value_objects.text_embedding import TextEmbedding
from infrastructure.llm.errors import translate_provider_errors

if TYPE_CHECKING:
    from infrastructure.config import Settings

logger = structlog.get_logger()

# Inputs per request: Gemini caps a batch at 100; OpenAI allows 2048 but also
# caps total tokens per request, and OpenRouter sits in front of both.
_BATCH_SIZE = {"gemini": 100, "openai": 128}
_TIMEOUT_SECONDS = 60.0


class ApiEmbeddingGenerator:
    def __init__(self, spec: EmbeddingSpec, dimensions: int) -> None:
        self._spec = spec
        self._dimensions = dimensions
        self._client: Any = None

    def _get_client(self) -> Any:  # one of two SDK clients
        if self._client is None:
            if self._spec.sdk == "gemini":
                from google import genai

                self._client = genai.Client(api_key=self._spec.api_key).aio
            else:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=self._spec.api_key,
                    base_url=self._spec.base_url,
                    timeout=_TIMEOUT_SECONDS,
                )
        return self._client

    async def _call(self, batch: list[str]) -> list[list[float]]:
        client = self._get_client()
        if self._spec.sdk == "gemini":
            from google.genai import types

            resp = await client.models.embed_content(
                model=self._spec.provider_model,
                # One Content per text: Gemini Embedding 2 folds the parts of a
                # single Content into one vector.
                contents=[types.Content(parts=[types.Part(text=t)]) for t in batch],
                config=types.EmbedContentConfig(output_dimensionality=self._dimensions),
            )
            vectors = [list(e.values or []) for e in resp.embeddings or []]
        else:
            resp = await client.embeddings.create(
                model=self._spec.provider_model,
                input=batch,
                dimensions=self._dimensions,
            )
            vectors = [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
        if len(vectors) != len(batch):
            msg = (
                f"Embedding provider returned {len(vectors)} vectors for {len(batch)} "
                f"inputs ({self._spec.provider_model})"
            )
            raise LLMBadRequestError(msg)
        return vectors

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        if self._spec.missing_key_message or not self._spec.api_key:
            raise LLMNotConfiguredError(
                self._spec.missing_key_message or "No API key configured for embeddings."
            )
        size = _BATCH_SIZE[self._spec.sdk]
        vectors: list[list[float]] = []
        with translate_provider_errors():
            for start in range(0, len(texts), size):
                vectors += await self._call(texts[start : start + size])
        if any(len(v) != self._dimensions for v in vectors):
            msg = (
                f"{self._spec.provider_model} returned {len(vectors[0])}-dimensional "
                f"vectors; the vector store expects {self._dimensions}"
            )
            raise LLMBadRequestError(msg)
        return vectors

    def _to_embedding(self, vector: list[float]) -> TextEmbedding:
        return TextEmbedding(
            embedding_id=uuid4(),
            vector=vector,
            model_name=self._spec.model,
            dimensions=len(vector),
            generated_at=datetime.now(UTC),
        )

    async def generate_text_embedding(
        self,
        text: str,
        model_name: str | None = None,
    ) -> TextEmbedding:
        if not text or not text.strip():
            msg = "Text cannot be empty"
            raise ValueError(msg)
        [vector] = await self._embed([self._spec.query_prefix + text])
        return self._to_embedding(vector)

    async def generate_batch_embeddings(
        self,
        texts: list[str],
        model_name: str | None = None,
    ) -> list[TextEmbedding]:
        if not texts:
            msg = "Texts list cannot be empty"
            raise ValueError(msg)
        for i, text in enumerate(texts):
            if not text or not text.strip():
                msg = f"Text at index {i} cannot be empty"
                raise ValueError(msg)
        vectors = await self._embed([self._spec.document_prefix + t for t in texts])
        logger.debug("api_batch_embeddings_generated", count=len(vectors), model=self._spec.model)
        return [self._to_embedding(v) for v in vectors]

    async def get_model_info(self) -> dict[str, str | int]:
        return {
            "model_name": self._spec.model,
            "dimensions": self._dimensions,
            "provider": self._spec.sdk,
            "device": "api",
        }


def env_embedding_spec(settings: Settings) -> EmbeddingSpec:
    """The server-wide API model (EMBEDDING_MODEL_PROVIDER other than sentence-transformers).

    A missing key is legal at boot (BYO-key deployments): every call then fails
    closed with LLMNotConfiguredError instead of the process refusing to start.
    """
    provider = settings.embedding_model_provider
    model = settings.embedding_model_name
    api_key = settings.embedding_api_key or {
        "openai": settings.openai_api_key,
        "gemini": settings.google_api_key,
    }.get(provider)
    # Known models bring their task prefixes unless the operator set their own.
    preset = next(
        (p for p in EMBEDDING_MODELS.values() if p.providers.get(provider) == model), None
    )
    base_url = settings.embedding_base_url if provider == "openai" else None
    return EmbeddingSpec(
        model=model,
        sdk="gemini" if provider == "gemini" else "openai",
        provider_model=model,
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL if provider == "openrouter" else base_url,
        query_prefix=settings.embedding_query_prefix or (preset.query_prefix if preset else ""),
        document_prefix=settings.embedding_document_prefix
        or (preset.document_prefix if preset else ""),
        missing_key_message=None
        if api_key
        else f"EMBEDDING_MODEL_PROVIDER={provider} needs EMBEDDING_API_KEY.",
    )
