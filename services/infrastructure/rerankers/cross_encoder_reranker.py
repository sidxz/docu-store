"""Cross-encoder reranker using sentence-transformers.

Scores each (query, passage) pair jointly for much higher precision
than independent bi-encoder embeddings. Used as Stage 2 after vector retrieval.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal

import structlog

from application.ports.reranker import Reranker, RerankDocument, RerankResult

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder as _CrossEncoder

logger = structlog.get_logger()


class CrossEncoderReranker(Reranker):
    """Reranker using a cross-encoder model from sentence-transformers."""

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
        device: Literal["cpu", "cuda", "mps"] = "cpu",
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._model: _CrossEncoder | None = None

        logger.info(
            "initializing_cross_encoder_reranker",
            model_name=model_name,
            device=device,
        )

    def _ensure_model_loaded(self) -> None:
        """Lazy load the cross-encoder model on first use."""
        if self._model is None:
            from sentence_transformers import CrossEncoder  # noqa: PLC0415

            self._model = CrossEncoder(self.model_name, device=self.device)
            logger.info("cross_encoder_model_loaded", model_name=self.model_name)

    def rerank(
        self,
        query: str,
        documents: list[RerankDocument],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """Score each (query, document) pair and re-sort by cross-encoder score."""
        if not documents:
            return []

        self._ensure_model_loaded()

        pairs = [(query, doc.text) for doc in documents]
        scores = self._model.predict(pairs)

        results = [
            RerankResult(
                id=doc.id,
                score=float(score) if not math.isnan(float(score)) else -100.0,
                original_rank=i,
            )
            for i, (doc, score) in enumerate(zip(documents, scores))
        ]

        results.sort(key=lambda r: r.score, reverse=True)

        if top_k:
            results = results[:top_k]

        logger.info(
            "rerank_completed",
            query_length=len(query),
            candidates=len(documents),
            returned=len(results),
        )

        return results
