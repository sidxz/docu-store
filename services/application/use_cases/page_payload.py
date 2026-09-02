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
    from domain.aggregates.page import Page
    from domain.value_objects.source_class import SourceClass


def build_page_payload(page: Page, source_class: SourceClass) -> dict:
    """Payload fields derived from a page, plus the provenance of its artifact.

    ``source_class`` is written unconditionally while everything else is
    conditional: a point missing it matches no provenance filter, so it drops
    out of a filtered search rather than failing it.
    """
    payload: dict = {"source_class": str(source_class)}

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
