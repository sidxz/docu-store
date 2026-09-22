"""The Qdrant payload for one page.

There are two paths that embed pages — one page at a time, and the batch
re-embed the ingestion pipeline actually uses — and they had grown identical
copies of this dict. A field added to one of them is a field that silently is
not there, which is exactly what happened to ``source_class``: it went into the
single-page builder, the pipeline ran the batch one, and every point was written
without it. Both call this now.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.services.compound_alias_resolver import is_alias, synonyms_of

if TYPE_CHECKING:
    from collections.abc import Iterable

    from domain.aggregates.artifact import Artifact
    from domain.aggregates.page import Page
    from domain.value_objects.source_class import SourceClass
    from domain.value_objects.tag_mention import TagMention


def filter_names(tag_mentions: Iterable[TagMention] | None) -> list[str]:
    """Lowercased names an entity filter can match: each tag plus every name a compound
    goes by. The card is named CHEMBL6109008, but a question may ask about "8l", its
    deck label; filters match this list, never the display tags.
    """
    names: list[str] = []
    for tm in tag_mentions or []:
        names.append(tm.tag.lower())
        if tm.entity_type == "compound_name":
            names.extend(s.lower() for s in synonyms_of(tm) if is_alias(s))
    return list(dict.fromkeys(names))


def table_scope_candidates(
    tag_mentions: Iterable[TagMention] | None,
) -> list[tuple[str, str | None, list[str]]]:
    """Candidates for ``scope_table_entities``: each tag, its type, and every name it
    goes by. A table prints the deck label ("8d") while its card is named by the registry
    ID, so matching the display tag alone left the table holding the values untagged —
    and a table chunk's tags override the page-wide ones.
    """
    return [(tm.tag, tm.entity_type, filter_names([tm])) for tm in tag_mentions or []]


def artifact_tag_normalized(artifact: Artifact | None) -> list[str]:
    """Lowercased artifact-level tags: aggregated tags, authors, publication year.

    This is the field the ``any`` tag-match mode ORs against the page-level tags,
    so a document *about* a topic matches on every one of its pages, not only the
    pages that happen to spell the topic out.
    """
    if artifact is None:
        return []
    tags: list[str] = []
    if artifact.tag_mentions:
        tags.extend(filter_names(artifact.tag_mentions))
    if artifact.author_mentions:
        tags.extend(am.name.lower() for am in artifact.author_mentions)
    if artifact.presentation_date and artifact.presentation_date.date:
        tags.append(str(artifact.presentation_date.date.year))
    return tags


def build_page_payload(
    page: Page,
    source_class: SourceClass,
    artifact: Artifact | None,
) -> dict:
    """Payload fields derived from a page, plus the provenance of its artifact.

    ``source_class`` is written unconditionally while everything else is
    conditional: a point missing it matches no provenance filter, so it drops
    out of a filtered search rather than failing it.

    ``artifact`` is required rather than defaulted because the artifact-level
    tags have to be written *here*, at point creation. They used to be patched on
    afterwards by SyncArtifactMetadataToVectorStoreUseCase, and an upsert deletes
    and recreates its points -- so every re-embed silently dropped them, and the
    batch re-embed runs at the end of ingestion. Half the corpus ended up with no
    artifact tags at all, which quietly turned ``any`` tag matching into
    ``page_any``. The sync use case still exists for the reverse ordering (tags
    aggregated after the pages were embedded); between the two, either order works.
    """
    payload: dict = {"source_class": str(source_class)}

    artifact_tags = artifact_tag_normalized(artifact)
    if artifact_tags:
        payload["artifact_tag_normalized"] = artifact_tags

    if page.workspace_id:
        payload["workspace_id"] = str(page.workspace_id)

    if page.tag_mentions:
        payload["tags"] = [tm.tag for tm in page.tag_mentions]
        payload["tag_normalized"] = filter_names(page.tag_mentions)
        ner_types = {tm.entity_type for tm in page.tag_mentions if tm.entity_type}
        payload["entity_types"] = sorted(ner_types)

    if page.compound_mentions:
        payload["compound_smiles"] = [
            cm.canonical_smiles
            for cm in page.compound_mentions
            if cm.canonical_smiles and cm.is_smiles_valid
        ]

    return payload
