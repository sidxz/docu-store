"""Accumulates and deduplicates retrieval results across iterative searches."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from infrastructure.chat.models import RetrievalResult
from infrastructure.config import settings

if TYPE_CHECKING:
    from application.dtos.chat_dtos import SourceCitationDTO

log = structlog.get_logger(__name__)


class RetrievalAccumulator:
    """Tracks all sources gathered across iterative agentic searches.

    Provides dedup, budget tracking, and query tracking to prevent
    the model from repeating the same search.
    """

    def __init__(self, budget_chars: int | None = None) -> None:
        self._results: dict[str, RetrievalResult] = {}  # dedup_key -> result
        self._budget = budget_chars or settings.chat_context_budget_chars
        self._chars_used = 0
        self._queries_seen: set[str] = set()

    def add_results(self, results: list[RetrievalResult], query_source: str = "") -> int:
        """Add results, deduplicating against existing ones.

        Returns:
            Number of *new* results added (not duplicates).

        """
        added = 0
        for r in results:
            key = self._dedup_key(r)
            if key in self._results:
                # Keep the higher-scoring version
                existing = self._results[key]
                if self._score(r) > self._score(existing):
                    self._chars_used -= len(existing.expanded_text)
                    self._results[key] = r
                    self._chars_used += len(r.expanded_text)
                continue

            self._results[key] = r
            self._chars_used += len(r.expanded_text)
            added += 1

        if query_source:
            self._queries_seen.add(query_source.lower().strip())

        log.debug(
            "accumulator.add",
            new=added,
            total=len(self._results),
            chars_used=self._chars_used,
            budget=self._budget,
        )
        return added

    def seed_carried_forward(self, citations: list[SourceCitationDTO]) -> int:
        """Seed the accumulator with citations from the previous grounded turn.

        Converts SourceCitationDTOs to RetrievalResults with a low baseline score
        so they participate in context assembly but don't dominate high-relevance slots.

        Returns:
            Number of new results seeded.

        """
        results: list[RetrievalResult] = []
        for c in citations:
            results.append(
                RetrievalResult(
                    source_type="chunk",
                    artifact_id=c.artifact_id,
                    artifact_title=c.artifact_title,
                    authors=c.authors,
                    presentation_date=c.presentation_date,
                    page_id=c.page_id,
                    page_index=c.page_index,
                    page_name=c.page_name,
                    expanded_text=c.text_excerpt or "",
                    matched_text=c.text_excerpt or "",
                    similarity_score=0.5,
                    query_source="carried_forward",
                ),
            )
        added = self.add_results(results, "carried_forward")
        log.info("accumulator.seed_carried_forward", seeded=added, total_citations=len(citations))
        return added

    def get_all_results(self) -> list[RetrievalResult]:
        """Return all accumulated results sorted by score (descending)."""
        results = list(self._results.values())
        results.sort(key=self._score, reverse=True)
        return results

    def summary_for_model(self) -> str:
        """Brief summary for the LLM about what's been gathered so far."""
        total = len(self._results)
        unique_artifacts = len({r.artifact_id for r in self._results.values()})
        chunks = sum(1 for r in self._results.values() if r.source_type == "chunk")
        summaries = total - chunks

        return (
            f"Found {total} sources from {unique_artifacts} documents so far "
            f"({chunks} text chunks, {summaries} summaries). "
            f"Context budget: {self._chars_used}/{self._budget} chars used."
        )

    def is_at_capacity(self) -> bool:
        """Check if accumulated context has reached the budget."""
        return self._chars_used >= self._budget

    def has_seen_query(self, query: str) -> bool:
        """Check if this query (or very similar) was already executed."""
        return query.lower().strip() in self._queries_seen

    @property
    def result_count(self) -> int:
        return len(self._results)

    @property
    def chars_used(self) -> int:
        return self._chars_used

    @staticmethod
    def _dedup_key(r: RetrievalResult) -> str:
        """Same dedup logic as IntelligentRetrievalNode.

        Tool-generated synthetic results (structure, bioactivity) use their own
        namespace so they don't collide with raw page content — they carry
        different information (e.g., SMILES annotation vs. full page text).
        """
        if r.query_source.startswith("tool_structure:") or r.query_source.startswith("tool_bioactivity:"):
            return f"{r.query_source}:{r.page_id or r.artifact_id}"
        if r.source_type == "chunk" and r.page_id:
            return f"chunk:{r.page_id}"
        if r.source_type == "summary":
            return f"summary:{r.artifact_id}:{r.page_id or 'artifact'}"
        return f"{r.source_type}:{r.artifact_id}:{r.page_id}"

    @staticmethod
    def _score(r: RetrievalResult) -> float:
        return r.rerank_score if r.rerank_score is not None else r.similarity_score
