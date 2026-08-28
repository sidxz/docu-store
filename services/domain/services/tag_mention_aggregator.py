"""Domain service: aggregate tag mentions from multiple pages into artifact-level tags.

Deduplicates tags across pages by (entity_type, normalized tag name).
For compound_name entities the key is first resolved through the document's
alias map, so an alias declared on one page ("CHEMBL4443524, aka TAM16") also
merges the bare mentions on every other page; bioactivities and synonyms are
then merged across the whole group.
For all other entity types, the highest-confidence mention is kept.

Provenance is tracked: each aggregated tag records which pages contributed it
via ``TagSource`` entries in the ``sources`` field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.services.compound_alias_resolver import (
    build_alias_map,
    merge_alias_group,
    normalize,
)
from domain.value_objects.tag_mention import TagMention, TagSource

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID


def aggregate_tag_mentions(
    pages_data: list[tuple[UUID, int, list[TagMention]]],
    structures: Mapping[str, str | None] | None = None,
) -> list[TagMention]:
    """Merge tag mentions from multiple pages into a deduplicated artifact-level list.

    Each page's tags are tracked with provenance so that the resulting artifact-level
    tags know which pages they originated from.

    Parameters
    ----------
    pages_data:
        One tuple per page: ``(page_id, page_index, tag_mentions)``.
    structures:
        Compound label → resolved SMILES across the artifact, used to refuse an
        alias merge between two labels whose structures disagree.

    Returns
    -------
    A single deduplicated list suitable for ``Artifact.update_tag_mentions()``,
    with ``sources``, ``tag_normalized``, ``max_confidence``, and ``page_count``
    populated on each entry.

    """
    alias_map = build_alias_map(
        (tm for _, _, page_tags in pages_data for tm in page_tags),
        structures,
    )

    # Group by (entity_type, normalized tag) → list of (TagMention, page_id, page_index)
    groups: dict[tuple[str, str], list[tuple[TagMention, UUID, int]]] = {}
    for page_id, page_index, page_tags in pages_data:
        for tm in page_tags:
            norm = normalize(tm.tag)
            if tm.entity_type == "compound_name":
                norm = alias_map.get(norm, norm)
            groups.setdefault((tm.entity_type or "other", norm), []).append(
                (tm, page_id, page_index),
            )

    if not groups:
        return []

    result: list[TagMention] = []
    for (etype, norm_tag), entries in groups.items():
        mentions = [e[0] for e in entries]

        if etype == "compound_name":
            base = merge_alias_group(mentions, norm_tag)
        else:
            base = _pick_best(mentions)

        # Build provenance sources
        sources = [
            TagSource(
                page_id=page_id,
                page_index=page_index,
                confidence=tm.confidence,
            )
            for tm, page_id, page_index in entries
        ]

        # Deduplicate sources by page_id (a page may have the same tag twice)
        seen_pages: set[UUID] = set()
        deduped_sources: list[TagSource] = []
        for src in sources:
            if src.page_id not in seen_pages:
                seen_pages.add(src.page_id)
                deduped_sources.append(src)

        confidences = [s.confidence for s in deduped_sources if s.confidence is not None]
        max_conf = max(confidences) if confidences else None

        result.append(
            base.model_copy(
                update={
                    "tag_normalized": normalize(base.tag),
                    "sources": deduped_sources,
                    "max_confidence": max_conf,
                    "page_count": len(deduped_sources),
                },
            ),
        )

    return result


def _pick_best(mentions: list[TagMention]) -> TagMention:
    """Return the TagMention with the highest confidence (or first if all None)."""
    best = mentions[0]
    for tm in mentions[1:]:
        if tm.confidence is not None and (
            best.confidence is None or tm.confidence > best.confidence
        ):
            best = tm
    return best
