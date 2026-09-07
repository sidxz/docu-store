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

# A candidate scoring below this was not judged relevant-or-not; the model failed
# to judge it at all, and the number it returned is noise rather than a ranking. Measured on this
# corpus: a passage the model recognises scores 0.73-0.99, while a query it
# cannot match collapses the whole distribution below 0.04 -- including the
# passages that hold the answer. Sorting on that is worse than not sorting,
# because it also overwrites the first-stage similarity that did find them.
#
# The default is the MEDIUM tier line the assembly stage already uses: if not
# one candidate clears the bar for "worth more than 200 characters", there is
# nothing to rank. It is a Settings field because it is calibrated against a
# specific model's score distribution and has to be retuned when that changes.
_DEFAULT_ABSTAIN_FLOOR = 0.05


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
        abstain_floor: float = _DEFAULT_ABSTAIN_FLOOR,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.abstain_floor = abstain_floor
        self._model: _CrossEncoder | None = None
        self._lock = threading.Lock()

        logger.info(
            "initializing_cross_encoder_reranker",
            model_name=model_name,
            device=device,
            abstain_floor=abstain_floor,
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

        Any candidate scoring below :attr:`abstain_floor` comes back with
        ``score=None`` rather than a near-zero float -- the model failed to judge
        it, which is not the same claim as "scored, and terrible". Those keep the
        first-stage order, behind everything that was scored. See
        :data:`_DEFAULT_ABSTAIN_FLOOR`.
        """
        if not documents:
            return []

        self._ensure_model_loaded()

        pairs = [(query, doc.text) for doc in documents]
        scores = self._model.predict(pairs)

        results: list[RerankResult] = []
        # 0 = scored, 1 = below the floor, 2 = nan. Sorting on this before the
        # score keeps the three groups in that order without comparing a
        # probability against None.
        rank_group: dict[int, int] = {}
        abstained_count = 0

        for i, (doc, raw) in enumerate(zip(documents, scores)):
            value = float(raw)
            if math.isnan(value):
                # A degenerate passage was not judged, and must not displace one
                # that was. It sorts behind even the unscored.
                score, group = None, 2
            else:
                calibrated = _sigmoid(value)
                if calibrated < self.abstain_floor:
                    # Below the floor the model is not expressing weak relevance,
                    # it is failing to judge: measured on this corpus a passage it
                    # recognises scores 0.73-0.99, and a query it cannot match
                    # collapses to 0.000x whether or not the passage is the answer.
                    # Passing that on as a score is worse than passing nothing,
                    # because a real number outranks the first-stage similarity
                    # that did find the passage.
                    #
                    # Judged per candidate, not per batch. A single lexical false
                    # positive -- a title slide sharing words with the question --
                    # scoring above the floor must not certify the rest of the
                    # pool: on the HARD-0305 deck exactly that happened, and a
                    # batch-level max() test left ten collapsed gold slides
                    # tiered LOW behind it.
                    score, group = None, 1
                    abstained_count += 1
                else:
                    score, group = calibrated, 0
            rank_group[i] = group
            results.append(RerankResult(id=doc.id, score=score, original_rank=i))

        if abstained_count:
            logger.info(
                "rerank_abstained",
                query_length=len(query),
                candidates=len(documents),
                abstained=abstained_count,
                abstain_floor=self.abstain_floor,
            )

        # Scored candidates by score; everything the model could not judge keeps
        # the first-stage order behind them, which is the ranking it was going to
        # fall back to anyway.
        results.sort(
            key=lambda r: (
                rank_group[r.original_rank],
                -r.score if r.score is not None else r.original_rank,
            )
        )

        if top_k:
            results = results[:top_k]

        logger.info(
            "rerank_completed",
            query_length=len(query),
            candidates=len(documents),
            returned=len(results),
        )

        return results
