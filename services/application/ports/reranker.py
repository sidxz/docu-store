"""Port for cross-encoder reranking."""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class RerankDocument:
    """A document to be scored against a query."""

    id: str
    text: str


@dataclass
class RerankResult:
    """A reranked document with its relevance score.

    ``score`` is a calibrated probability in (0, 1), never a raw logit. Cross
    encoders emit unbounded logits; squashing them is the adapter's job so that
    no caller has to remember to do it, and so a score can be compared against a
    probability-shaped threshold or averaged with a cosine similarity. 0.0 is
    reserved as an "unscored" sentinel and is strictly below every real score.

    ``score`` is ``None`` when the reranker abstained: no candidate cleared the
    floor, so its ordering carries no signal and callers must fall back to the
    first-stage similarity. Every consumer already spells that fallback
    ``r.rerank_score if r.rerank_score is not None else r.similarity_score``, so
    None routes through the path they already have. A near-zero float would not:
    it reads as "scored, and terrible", which is a claim the model did not make.
    """

    id: str
    score: float | None
    original_rank: int


class Reranker(Protocol):
    """Port for two-stage reranking of retrieval results."""

    def rerank(
        self,
        query: str,
        documents: list[RerankDocument],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """Score (query, document) pairs and return sorted by relevance.

        Args:
            query: The search query text.
            documents: Candidate documents from Stage 1 retrieval.
            top_k: If set, return only top-k results.

        Returns:
            Results sorted by cross-encoder score (descending).

        """
        ...
