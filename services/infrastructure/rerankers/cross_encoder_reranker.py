"""Cross-encoder reranker using sentence-transformers.

Scores each (query, passage) pair jointly for much higher precision
than independent bi-encoder embeddings. Used as Stage 2 after vector retrieval.
"""

from __future__ import annotations

import math
import threading
from typing import TYPE_CHECKING, Literal

import structlog

from application.ports.reranker import RerankDocument, Reranker, RerankResult

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder as _CrossEncoder

logger = structlog.get_logger()

# Below this the sigmoid underflows to 0.0, which is the sentinel callers use for
# "not scored"; clamping keeps every real score strictly above it.
_LOGIT_CLAMP = 30.0


def _sigmoid(x: float) -> float:
    """Squash a cross-encoder logit into (0, 1).

    ms-marco cross-encoders are trained with a BCE-with-logits objective and ship
    with ``num_labels=1`` and an ``Identity()`` activation, so ``predict`` returns
    an unbounded logit -- measured range on this corpus is about -11.3 to +4.0.
    Every threshold downstream is written as a probability, so the squash belongs
    here, at the single point all callers route through, rather than in each of
    them. Sigmoid is the inverse of the training link, so this is calibration
    rather than an arbitrary rescale. It is order-preserving, so ranking is
    unchanged. Clamped because ``math.exp`` overflows around 710.
    """
    return 1.0 / (1.0 + math.exp(-max(-_LOGIT_CLAMP, min(_LOGIT_CLAMP, x))))


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
        self._lock = threading.Lock()

        logger.info(
            "initializing_cross_encoder_reranker",
            model_name=model_name,
            device=device,
        )

    def _ensure_model_loaded(self) -> None:
        """Lazy load the cross-encoder model on first use (thread-safe double-check locking)."""
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, device=self.device)
            logger.info("cross_encoder_model_loaded", model_name=self.model_name)

    def rerank(
        self,
        query: str,
        documents: list[RerankDocument],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """Score each (query, document) pair and re-sort by relevance.

        Scores are calibrated probabilities in (0, 1), not raw logits -- see
        :func:`_sigmoid`. Compare them against probability-shaped thresholds.
        """
        if not documents:
            return []

        self._ensure_model_loaded()

        pairs = [(query, doc.text) for doc in documents]
        scores = self._model.predict(pairs)

        results = [
            RerankResult(
                id=doc.id,
                # A nan (empty/degenerate passage) must sort last, so it keeps a
                # logit far below any real one and squashes with everything else.
                score=_sigmoid(float(score) if not math.isnan(float(score)) else -100.0),
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
