"""Domain service: aggregate tag mentions from multiple pages into artifact-level tags.

Deduplicates tags across pages by (entity_type, normalized tag name).
For compound_name entities, bioactivities and synonyms are merged across pages.
For all other entity types, the highest-confidence mention is kept.

Provenance is tracked: each aggregated tag records which pages contributed it
via ``TagSource`` entries in the ``sources`` field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.value_objects.tag_mention import TagMention, TagSource

if TYPE_CHECKING:
    from uuid import UUID


def _normalize(name: str) -> str:
    """Lowercase, strip, and collapse whitespace for tag matching."""
    return name.strip().lower().replace(" ", "")


def aggregate_tag_mentions(
    pages_data: list[tuple[UUID, int, list[TagMention]]],
) -> list[TagMention]:
    """Merge tag mentions from multiple pages into a deduplicated artifact-level list.

    Each page's tags are tracked with provenance so that the resulting artifact-level
    tags know which pages they originated from.

    Parameters
    ----------
    pages_data:
        One tuple per page: ``(page_id, page_index, tag_mentions)``.

    Returns
    -------
    A single deduplicated list suitable for ``Artifact.update_tag_mentions()``,
    with ``sources``, ``tag_normalized``, ``max_confidence``, and ``page_count``
    populated on each entry.
    """
    # Group by (entity_type, normalized tag) → list of (TagMention, page_id, page_index)
    groups: dict[tuple[str, str], list[tuple[TagMention, UUID, int]]] = {}
    for page_id, page_index, page_tags in pages_data:
        for tm in page_tags:
            key = (tm.entity_type or "other", _normalize(tm.tag))
            groups.setdefault(key, []).append((tm, page_id, page_index))

    if not groups:
        return []

    result: list[TagMention] = []
    for (etype, norm_tag), entries in groups.items():
        mentions = [e[0] for e in entries]

        if etype == "compound_name":
            base = _merge_compound_group(mentions)
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
                    "tag_normalized": norm_tag,
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


def _merge_compound_group(mentions: list[TagMention]) -> TagMention:
    """Merge multiple occurrences of the same compound across pages.

    - Picks the best-confidence TagMention as the base.
    - Merges all ``bioactivities`` lists.
    - Merges ``synonyms`` (union, comma-separated).
    """
    base = _pick_best(mentions)

    # Collect all bioactivities across pages
    all_activities: list[dict] = []
    all_synonyms: set[str] = set()

    for tm in mentions:
        params = tm.additional_model_params or {}
        activities = params.get("bioactivities")
        if isinstance(activities, list):
            all_activities.extend(activities)
        synonyms_str = params.get("synonyms")
        if isinstance(synonyms_str, str) and synonyms_str.strip():
            for s in synonyms_str.split(","):
                s = s.strip()
                if s:
                    all_synonyms.add(s)

    # Deduplicate bioactivities by (assay_type, value, unit)
    seen: set[tuple[str, str, str]] = set()
    deduped_activities: list[dict] = []
    for a in all_activities:
        key = (a.get("assay_type", ""), a.get("value", ""), a.get("unit", ""))
        if key not in seen:
            seen.add(key)
            deduped_activities.append(a)

    # Build updated params
    updated_params = dict(base.additional_model_params or {})
    if deduped_activities:
        updated_params["bioactivities"] = deduped_activities
    if all_synonyms:
        updated_params["synonyms"] = ", ".join(sorted(all_synonyms))

    return base.model_copy(update={"additional_model_params": updated_params})
