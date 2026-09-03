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
    """

    id: str
    score: float
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
