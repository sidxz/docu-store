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

if TYPE_CHECKING:
    from domain.aggregates.artifact import Artifact
    from domain.aggregates.page import Page
    from domain.value_objects.source_class import SourceClass


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
        tags.extend(tm.tag.lower() for tm in artifact.tag_mentions)
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
        payload["tag_normalized"] = [tm.tag.lower() for tm in page.tag_mentions]
        ner_types = {tm.entity_type for tm in page.tag_mentions if tm.entity_type}
        payload["entity_types"] = sorted(ner_types)

    if page.compound_mentions:
        payload["compound_smiles"] = [
            cm.canonical_smiles
            for cm in page.compound_mentions
            if cm.canonical_smiles and cm.is_smiles_valid
        ]

    return payload
