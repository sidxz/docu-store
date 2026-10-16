"""Per-workspace text embeddings (self-serve).

Every vector in a workspace must come from one model, and a query must be
embedded by that same model — so the model is a workspace setting, resolved by
``UserLLMScope`` into a contextvar together with the workspace's key. ``None``
there means "the server model"; a spec means an API model through that key. Reached without any scope it raises rather than guess: the server model
would silently embed into the wrong space.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from infrastructure.embeddings.api_embedding_generator import ApiEmbeddingGenerator
from infrastructure.llm import llm_context

if TYPE_CHECKING:
    from application.ports.embedding_generator import EmbeddingGenerator
    from application.services.embedding_models import EmbeddingSpec
    from domain.value_objects.text_embedding import TextEmbedding

_CACHE_SIZE = 32  # one client per (model, key); rebuilt cheaply on eviction


class ScopedEmbeddingGenerator:
    def __init__(self, server: EmbeddingGenerator, dimensions: int) -> None:
        self._server = server
        self._dimensions = dimensions
        self._api: OrderedDict[EmbeddingSpec, ApiEmbeddingGenerator] = OrderedDict()

    def _target(self) -> EmbeddingGenerator:
        spec = llm_context.get_embedding_spec()
        if spec is llm_context.NOT_SCOPED:
            msg = "Text embedding outside a workspace scope (UserLLMScope.for_workspace)."
            raise RuntimeError(msg)
        if spec is None:
            return self._server
        generator = self._api.pop(spec, None) or ApiEmbeddingGenerator(spec, self._dimensions)
        self._api[spec] = generator
        if len(self._api) > _CACHE_SIZE:
            self._api.popitem(last=False)
        return generator

    async def generate_text_embedding(
        self,
        text: str,
        model_name: str | None = None,
    ) -> TextEmbedding:
        return await self._target().generate_text_embedding(text)

    async def generate_batch_embeddings(
        self,
        texts: list[str],
        model_name: str | None = None,
    ) -> list[TextEmbedding]:
        return await self._target().generate_batch_embeddings(texts)

    async def get_model_info(self) -> dict[str, str | int]:
        """The server model — what health checks and warm-up care about."""
        return await self._server.get_model_info()
