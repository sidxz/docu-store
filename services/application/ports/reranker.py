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
    """A reranked document with cross-encoder score."""

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
