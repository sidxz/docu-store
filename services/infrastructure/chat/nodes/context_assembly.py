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

# Relevance thresholds
_HIGH_RERANK = 0.7
_HIGH_SIM = 0.85
_MED_RERANK = 0.4
_MED_SIM = 0.6


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

    def _tier_results(
        self,
        results: list[RetrievalResult],
    ) -> tuple[list[RetrievalResult], list[RetrievalResult], list[RetrievalResult]]:
        high, medium, low = [], [], []
        for r in results:
            # Carried-forward sources go to MEDIUM regardless of score
            if r.query_source == "carried_forward":
                medium.append(r)
                continue

            # Bioactivity and structure results always HIGH (deterministic structured data)
            if r.query_source.startswith("tool_bioactivity:") or r.query_source.startswith("tool_structure:"):
                high.append(r)
                continue

            score = self._score(r)
            has_rerank = r.rerank_score is not None

            if (has_rerank and score > _HIGH_RERANK) or (not has_rerank and score > _HIGH_SIM):
                high.append(r)
            elif (has_rerank and score > _MED_RERANK) or (not has_rerank and score > _MED_SIM):
                medium.append(r)
            else:
                low.append(r)

        return high, medium, low

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

        for r in bio_high:
            text_len = len(r.expanded_text)
            if chars_used + text_len > budget:
                break
            selected.append(r)
            chars_used += text_len

        # High tier: full expanded text
        for r in other_high:
            text_len = len(r.expanded_text)
            if chars_used + text_len > budget:
                break
            selected.append(r)
            chars_used += text_len

        # Medium tier: matched chunk only (truncated to ~1000 chars)
        for r in medium:
            text_len = min(len(r.matched_text), 1000)
            if chars_used + text_len > budget:
                break
            selected.append(r)
            chars_used += text_len

        # Low tier: first 200 chars summary
        for r in low:
            text_len = min(len(r.expanded_text), 200)
            if chars_used + text_len > budget:
                break
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
                # Determine text to include based on tier
                score = self._score(r)
                has_rerank = r.rerank_score is not None
                is_high = (has_rerank and score > _HIGH_RERANK) or (
                    not has_rerank and score > _HIGH_SIM
                )
                is_low = not (
                    (has_rerank and score > _MED_RERANK) or (not has_rerank and score > _MED_SIM)
                )

                if is_high:
                    display_text = r.expanded_text
                elif is_low:
                    display_text = r.expanded_text[:200] + (
                        "..." if len(r.expanded_text) > 200 else ""
                    )
                else:
                    display_text = r.matched_text[:1000]

                # Format citation
                if r.query_source.startswith("tool_bioactivity:"):
                    compound_name = r.query_source.split(":", 1)[1] if ":" in r.query_source else ""
                    label = f"STRUCTURED BIOACTIVITY DATA for {compound_name}"
                elif r.query_source.startswith("tool_structure:"):
                    compound_name = r.query_source.split(":", 1)[1] if ":" in r.query_source else ""
                    label = f"COMPOUND STRUCTURE DATA for {compound_name}"
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
                    ),
                )
                idx += 1

        formatted = "\n\n".join(text_sections) if text_sections else "No relevant sources found."
        return citations, formatted
