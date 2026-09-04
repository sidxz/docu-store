"""Context assembly for Literature mode.

Split from ContextAssemblyNode rather than parameterised into it, for three
reasons that are all specific to this surface:

* Scale. Literature scores come from a cross-encoder logit through a sigmoid.
  The shared thresholds are tuned for bi-encoder cosine similarity, and reusing
  them puts almost every abstract in the LOW tier, where it is truncated to 200
  characters and stops being usable evidence.
* Shape. Every hit is its own artifact, and expanded_text, matched_text and the
  abstract are the same string. The chunk/summary dedup, the bioactivity tier and
  the group-by-artifact header are all dead code here.
* Budget. The shared hierarchical formatter emits a document header AND a
  per-citation label, so each paper's title is spent twice out of 12,000
  characters.
"""

from __future__ import annotations

import structlog

from application.dtos.chat_dtos import ChartSeriesDTO, ChartSpecDTO, SourceCitationDTO
from infrastructure.chat.models import ContextMetadata, RetrievalResult
from infrastructure.chat.nodes.context_assembly import ContextAssemblyNode
from infrastructure.config import settings

log = structlog.get_logger(__name__)


def build_provenance_spec(*, retrieved: int, assembled: int, cited: int) -> ChartSpecDTO:
    """What the answer stands on, at the three stages that can silently drop it.

    Not model-selected and not counted against the panel budget: it costs no
    request and no model call, and it is instrumentation rather than a finding.
    """
    return ChartSpecDTO(
        panel="provenance",
        title="Papers behind this answer",
        x_label="",
        y_label="Papers",
        categories=["Returned", "Assembled", "Cited"],
        series=[
            ChartSeriesDTO(
                name="Papers",
                points=[(0.0, float(retrieved)), (1.0, float(assembled)), (2.0, float(cited))],
            ),
        ],
    )


# Cut-points on the sigmoid of an ms-marco logit, from measurement on real
# abstracts (2026-09-02): an on-topic InhA inhibitor paper scored +1.23 (0.774),
# a "Correction to" notice -0.36 (0.411), a wrong-gene INHA paper -7.17 (0.0008).
_HIGH = 0.50   # logit 0.0 — carries its full abstract
_MEDIUM = 0.05  # logit -2.9 — carries a truncated abstract
_HIGH_CHARS = 3000  # a whole abstract, but never the whole budget
_MEDIUM_CHARS = 1000
_LOW_CHARS = 200


class LiteratureContextAssemblyNode(ContextAssemblyNode):
    """Assemble abstracts into a relevance-ordered, budgeted context."""

    def run(  # type: ignore[override]
        self,
        results: list[RetrievalResult],
    ) -> tuple[list[SourceCitationDTO], str, ContextMetadata]:
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

        budget = settings.chat_context_budget_chars
        ordered = sorted(results, key=self._score, reverse=True)

        citations: list[SourceCitationDTO] = []
        sections: list[str] = []
        chars_used = 0
        high_count = 0

        for r in ordered:
            score = self._score(r)
            if score >= _HIGH:
                display = r.expanded_text[:_HIGH_CHARS]
            elif score >= _MEDIUM:
                display = r.expanded_text[:_MEDIUM_CHARS]
            else:
                display = r.expanded_text[:_LOW_CHARS]

            if chars_used + len(display) > budget:
                # continue, not break: a long mid-ranked abstract must not shut
                # out every shorter one below it.
                continue

            idx = len(citations) + 1
            title = r.artifact_title or "Untitled"
            where = r.presentation_date or ""
            head = f"[{idx}] (ABSTRACT ONLY — {title}{f', {where}' if where else ''})"
            sections.append(f"{head}\n{display}")
            chars_used += len(display)
            if score >= _HIGH:
                high_count += 1

            citations.append(
                SourceCitationDTO(
                    artifact_id=r.artifact_id,
                    artifact_title=r.artifact_title,
                    authors=r.authors,
                    presentation_date=r.presentation_date,
                    page_id=None,
                    page_index=None,
                    page_name=None,
                    text_excerpt=r.matched_text[:500],
                    similarity_score=score,
                    citation_index=idx,
                    source_type="literature",
                    external_url=r.external_url,
                ),
            )

        if not citations:
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

        # Not ordered[: len(citations)] — continue (not break) above means
        # selected citations are no longer a prefix of `ordered`.
        scores = [c.similarity_score for c in citations]
        meta = ContextMetadata(
            total_sources=len(citations),
            high_relevance_count=high_count,
            avg_relevance_score=sum(scores) / len(scores) if scores else 0.0,
            unique_artifacts=len({c.artifact_id for c in citations}),
            has_summaries=False,
        )

        log.info(
            "literature.assembly.done",
            retrieved=len(results),
            selected=meta.total_sources,
            high=high_count,
            avg_score=f"{meta.avg_relevance_score:.3f}",
            chars_used=chars_used,
            budget=budget,
        )

        return citations, "\n\n".join(sections), meta
