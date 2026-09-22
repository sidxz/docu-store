"""Shared workspace-wide bioactivity assembly for a compound, looked up by name.

Single source of truth for the "walk the pages of every artifact tagged with the
compound, pull ``additional_model_params['bioactivities']`` off the matching
``compound_name`` tag mentions, dedup, collect synonyms, return matched pages"
logic. Feeds three consumers:

  - ``GET /compounds/{name}/profile`` (via ``GetCompoundProfileUseCase``)
  - the chat ``search_structured_bioactivity`` tool (markdown table for the LLM)
  - the chat molecule content block (structured ``BioactivityDTO`` list, feature F3)

Previously duplicated in ``GetCompoundProfileUseCase._collect_activity`` and
``SearchStructuredBioactivityTool.execute``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from application.dtos.compound_dtos import BioactivityDTO, CompoundPageRefDTO
from domain.services.compound_alias_resolver import synonyms_of, union_bioactivities

if TYPE_CHECKING:
    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.repositories.page_read_models import PageReadModel
    from application.ports.repositories.tag_dictionary_read_model import TagDictionaryReadModel

logger = structlog.get_logger()


class CompoundActivityQuery:
    """Assembles a compound's structured bioactivities, synonyms, and page refs.

    ACL-filtered. The optional ``target`` narrows the artifact set to those also
    tagged with that target/gene name (chat-tool behavior), unless none of them is;
    when ``target`` is None the intersection is skipped (profile behavior).
    """

    def __init__(
        self,
        tag_dictionary: TagDictionaryReadModel,
        page_read_model: PageReadModel,
        artifact_read_model: ArtifactReadModel,
    ) -> None:
        self._tag_dict = tag_dictionary
        self._pages = page_read_model
        self._artifacts = artifact_read_model

    async def documents_tagged(self, target: str, workspace_id: UUID) -> set[str]:
        """Artifact ids tagged with ``target`` as a target, else as a gene name."""
        ids = await self._tag_dict.get_artifact_ids_for_tag(
            target, entity_type="target", workspace_id=workspace_id,
        )
        if not ids:
            ids = await self._tag_dict.get_artifact_ids_for_tag(
                target, entity_type="gene_name", workspace_id=workspace_id,
            )
        return set(ids or [])

    async def collect(
        self,
        name: str,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
        target: str | None = None,
    ) -> tuple[list[BioactivityDTO], list[str], list[CompoundPageRefDTO]]:
        artifact_ids = await self._tag_dict.get_artifact_ids_for_tag(
            name, entity_type="compound_name", workspace_id=workspace_id,
        )
        if not artifact_ids:
            return [], [], []
        matched = set(artifact_ids)

        # Fail closed: an empty allowed list means "no accessible artifacts", not
        # "no filter" — match the `is not None` gate every vector/read store uses.
        if allowed_artifact_ids is not None:
            matched &= {str(a) for a in allowed_artifact_ids}

        # Optional target intersection — chat-tool behavior; skipped for profile. Only
        # when it leaves a document: decks spell one target differently ("sEH", "soluble
        # epoxide hydrolase"), so an empty intersection would report no data for a
        # compound that has rows. Each row names its own target; the tool says which.
        if target:
            matched = (matched & await self.documents_tagged(target, workspace_id)) or matched
        if not matched:
            return [], [], []
        matched_uuids = [UUID(a) for a in matched]

        titles: dict[str, str | None] = {}
        for aid in matched_uuids:
            try:
                art = await self._artifacts.get_artifact_by_id(aid, workspace_id=workspace_id)
                if art:
                    titles[str(aid)] = (
                        art.title_mention.title if art.title_mention else art.source_filename
                    )
            except Exception:
                logger.warning(
                    "compound_activity.artifact_lookup_failed", artifact_id=str(aid), exc_info=True,
                )

        pages = await self._pages.get_pages_by_artifact_ids(matched_uuids, workspace_id=workspace_id)

        activity_lists: list[list[dict]] = []
        synonyms: set[str] = set()
        refs: list[CompoundPageRefDTO] = []
        lname = name.lower()
        for page in pages:
            page_has = False
            for tm in page.tag_mentions:
                # Match the alias too: an aliased compound merges into one mention
                # under its canonical name, and callers still ask by either name.
                if tm.entity_type == "compound_name" and (
                    tm.tag.lower() == lname
                    or any(s.lower() == lname for s in synonyms_of(tm))
                ):
                    page_has = True
                    params = tm.additional_model_params or {}
                    # Stamp each row with its page before the union, so the row it keeps
                    # still says where it was read. The union's key ignores these fields.
                    page_of = {
                        "artifact_id": page.artifact_id,
                        "page_id": page.page_id,
                        "page_index": page.index,
                    }
                    rows = params.get("bioactivities") or []
                    activity_lists.append([bio | page_of for bio in rows])
                    syn = params.get("synonyms")
                    if isinstance(syn, str) and syn.strip():
                        synonyms.update(s.strip() for s in syn.split(",") if s.strip())
            if page_has:
                refs.append(
                    CompoundPageRefDTO(
                        page_id=page.page_id,
                        page_index=page.index,
                        artifact_id=page.artifact_id,
                        artifact_title=titles.get(str(page.artifact_id)),
                    ),
                )
        bioactivities = [
            BioactivityDTO(
                assay_type=bio.get("assay_type", ""),
                value=bio.get("value", ""),
                unit=bio.get("unit") or None,
                raw_text=bio.get("raw_text") or None,
                assay=bio.get("assay") or None,
                strain=bio.get("strain") or None,
                target=bio.get("target") or None,
                combination=bio.get("combination") or None,
                artifact_id=bio["artifact_id"],
                page_id=bio["page_id"],
                page_index=bio["page_index"],
            )
            for bio in union_bioactivities(activity_lists)
        ]
        return bioactivities, sorted(synonyms), refs
