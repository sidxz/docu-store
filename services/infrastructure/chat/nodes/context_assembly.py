"""Stage 3 (Thinking Mode): Context Assembly.

Pure computation — no LLM calls. Deduplicates, tiers by relevance,
groups by artifact, enforces context budget.
"""

from __future__ import annotations

from collections import defaultdict

import structlog

from application.dtos.chat_dtos import SourceCitationDTO
from infrastructure.chat.models import ContextMetadata, RetrievalResult
from infrastructure.config import settings

log = structlog.get_logger(__name__)

# Relevance thresholds. Two pairs because two different scales arrive here: a
# reranker probability and a bi-encoder cosine are both in (0, 1) but are not the
# same quantity, so a single cut-point cannot serve both.
#
# The rerank cut-points are the ones measured for this cross-encoder on real
# text, and match LiteratureContextAssemblyNode. They used to be 0.7/0.4, which
# were cosine-shaped numbers compared against raw unbounded logits (roughly -11
# to +4): a nonsense comparison that put most reranked sources in LOW and cut
# them to 200 characters. The reranker now returns calibrated probabilities.
_HIGH_RERANK = 0.5  # sigmoid(0.0)
_MED_RERANK = 0.05  # sigmoid(-2.9)
_HIGH_SIM = 0.85
_MED_SIM = 0.6

# Per-source caps. HIGH is capped at all so that one long page cannot spend the
# whole budget and starve every source behind it.
_HIGH_CHARS = 3000
_MEDIUM_CHARS = 1000
_LOW_CHARS = 200


class ContextAssemblyNode:
    """Assemble retrieval results into tiered, hierarchical context."""

    def run(
        self,
        results: list[RetrievalResult],
    ) -> tuple[list[SourceCitationDTO], str, ContextMetadata]:
        """Assemble context from retrieval results.

        Returns:
            (citations, formatted_sources_text, context_metadata)

        """
        _debug = settings.chat_debug
        budget = settings.chat_context_budget_chars

        if not results:
            return (
                [],
                "No relevant sources found.",
                ContextMetadata(
                    total_sources=0,
                    high_relevance_count=0,
                    avg_relevance_score=0.0,
                    unique_artifacts=0,
                    has_summaries=False,
                ),
            )

        # Cross-source dedup: when chunk + summary from same page, keep chunk
        results = self._cross_source_dedup(results)

        # Tier results by relevance
        high, medium, low = self._tier_results(results)

        # Apply budget — drop low first, then truncate medium
        selected, chars_used = self._apply_budget(high, medium, low, budget)

        carried_forward_count = sum(1 for r in results if r.query_source == "carried_forward")
        bioactivity_count = sum(
            1 for r in results if r.query_source.startswith("tool_bioactivity:")
        )

        if _debug:
            log.info(
                "chat.debug.assembly.tiers",
                high=len(high),
                medium=len(medium),
                low=len(low),
                selected=len(selected),
                chars_used=chars_used,
                budget=budget,
                carried_forward=carried_forward_count,
                bioactivity=bioactivity_count,
            )

        # Group by artifact for hierarchical formatting
        citations, formatted = self._format_hierarchical(selected)

        # Build metadata
        scores = [self._score(r) for r in selected]
        meta = ContextMetadata(
            total_sources=len(selected),
            high_relevance_count=len([r for r in selected if r in high]),
            avg_relevance_score=sum(scores) / len(scores) if scores else 0.0,
            unique_artifacts=len({r.artifact_id for r in selected}),
            has_summaries=any(r.source_type == "summary" for r in selected),
        )

        log.info(
            "chat.assembly.done",
            total_sources=meta.total_sources,
            high_relevance=meta.high_relevance_count,
            avg_score=f"{meta.avg_relevance_score:.3f}",
            unique_artifacts=meta.unique_artifacts,
            carried_forward=carried_forward_count,
            bioactivity=bioactivity_count,
        )

        return citations, formatted, meta

    def _score(self, r: RetrievalResult) -> float:
        return r.rerank_score if r.rerank_score is not None else r.similarity_score

    def _tier_of(self, r: RetrievalResult) -> str:
        """Which relevance tier a source belongs to: high, medium or low.

        The single place this is decided. It used to be decided twice, once to
        size the budget and once to pick the text, from the same constants but by
        two independent expressions -- so a threshold edit applied to one and not
        the other would silently charge a source for text it never emitted.
        """
        # Carried-forward sources go to MEDIUM regardless of score
        if r.query_source == "carried_forward":
            return "medium"

        # Bioactivity and structure results always HIGH (deterministic structured data)
        if r.query_source.startswith(("tool_bioactivity:", "tool_structure:")):
            return "high"

        score = self._score(r)
        high, medium = (
            (_HIGH_RERANK, _MED_RERANK)
            if r.rerank_score is not None
            else (_HIGH_SIM, _MED_SIM)
        )
        if score > high:
            return "high"
        if score > medium:
            return "medium"
        return "low"

    def _display_text(self, r: RetrievalResult) -> str:
        """The exact text this source contributes, tier cap applied.

        Both the budget and the emitted prompt call this, so what a source is
        charged is by construction what it costs.
        """
        tier = self._tier_of(r)
        if tier == "high":
            # Structured tool output is exempt from the length cap: it is
            # deterministic, already privileged with reserved budget, and a
            # half-delivered assay table is worse than a long one -- the rows
            # past the cut read as "no such measurement" rather than as elided.
            # The cap exists to stop one long *page* starving the sources behind
            # it, and a page is never this.
            if r.query_source.startswith(("tool_bioactivity:", "tool_structure:")):
                return r.expanded_text
            return r.expanded_text[:_HIGH_CHARS]
        if tier == "medium":
            return r.matched_text[:_MEDIUM_CHARS]
        text = r.expanded_text[:_LOW_CHARS]
        return f"{text}..." if len(r.expanded_text) > _LOW_CHARS else text

    def _tier_results(
        self,
        results: list[RetrievalResult],
    ) -> tuple[list[RetrievalResult], list[RetrievalResult], list[RetrievalResult]]:
        buckets: dict[str, list[RetrievalResult]] = {"high": [], "medium": [], "low": []}
        for r in results:
            buckets[self._tier_of(r)].append(r)
        return buckets["high"], buckets["medium"], buckets["low"]

    def _cross_source_dedup(
        self,
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """When chunk + summary from same page, keep chunk, annotate."""
        chunk_pages = {r.page_id for r in results if r.source_type == "chunk" and r.page_id}
        deduped = []
        for r in results:
            # Drop summary if we already have a chunk from the same page
            if r.source_type == "summary" and r.page_id and r.page_id in chunk_pages:
                continue
            deduped.append(r)
        return deduped

    def _apply_budget(
        self,
        high: list[RetrievalResult],
        medium: list[RetrievalResult],
        low: list[RetrievalResult],
        budget: int,
    ) -> tuple[list[RetrievalResult], int]:
        selected: list[RetrievalResult] = []
        chars_used = 0

        # Bioactivity results get reserved budget first (deterministic, compact)
        bio_high = [r for r in high if r.query_source.startswith("tool_bioactivity:")]
        other_high = [r for r in high if not r.query_source.startswith("tool_bioactivity:")]

        for tier in (bio_high, other_high, medium, low):
            for r in tier:
                text_len = len(self._display_text(r))
                if chars_used + text_len > budget:
                    # continue, not break: one long source must not shut out
                    # every shorter one ranked below it. Skipping just the source
                    # that does not fit costs nothing and keeps the rest.
                    continue
                selected.append(r)
                chars_used += text_len

        return selected, chars_used

    def _format_hierarchical(
        self,
        results: list[RetrievalResult],
    ) -> tuple[list[SourceCitationDTO], str]:
        """Group by artifact, assign citation indices, format text."""
        # Group results by artifact
        by_artifact: dict[str, list[RetrievalResult]] = defaultdict(list)
        for r in results:
            by_artifact[str(r.artifact_id)].append(r)

        citations: list[SourceCitationDTO] = []
        text_sections: list[str] = []
        idx = 1

        for _aid, group in by_artifact.items():
            first = group[0]
            # Artifact header
            artifact_title = first.artifact_title or "Unknown Document"
            author_str = ", ".join(first.authors) if first.authors else ""
            date_str = first.presentation_date or ""
            header_parts = [f'=== Document: "{artifact_title}"']
            if author_str:
                header_parts.append(f"({author_str}")
                if date_str:
                    header_parts[-1] += f", {date_str})"
                else:
                    header_parts[-1] += ")"
            elif date_str:
                header_parts.append(f"({date_str})")
            header_parts.append("===")
            header = " ".join(header_parts)
            text_sections.append(header)

            for r in group:
                display_text = self._display_text(r)

                # Format citation
                if r.query_source.startswith("tool_bioactivity:"):
                    compound_name = r.query_source.split(":", 1)[1] if ":" in r.query_source else ""
                    label = f"STRUCTURED BIOACTIVITY DATA for {compound_name}"
                elif r.query_source.startswith("tool_structure:"):
                    compound_name = r.query_source.split(":", 1)[1] if ":" in r.query_source else ""
                    label = f"COMPOUND STRUCTURE DATA for {compound_name}"
                elif r.source_type == "literature":
                    label = f"ABSTRACT ONLY - {artifact_title}"
                elif r.source_type == "chunk":
                    label = f"Page {r.page_index}" if r.page_index is not None else "Page"
                    if r.page_name:
                        label = f"{r.page_name} (Page {r.page_index})"
                else:
                    label = f"Summary - {artifact_title}"

                text_sections.append(f"[{idx}] ({label})\n{display_text}")

                citations.append(
                    SourceCitationDTO(
                        artifact_id=r.artifact_id,
                        artifact_title=r.artifact_title,
                        authors=r.authors,
                        presentation_date=r.presentation_date,
                        page_id=r.page_id,
                        page_index=r.page_index,
                        page_name=r.page_name,
                        text_excerpt=r.matched_text[:500],
                        similarity_score=self._score(r),
                        citation_index=idx,
                        source_type=(
                            "literature" if r.source_type == "literature" else "document"
                        ),
                        external_url=r.external_url,
                    ),
                )
                idx += 1

        formatted = "\n\n".join(text_sections) if text_sections else "No relevant sources found."
        return citations, formatted
