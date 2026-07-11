from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from application.dtos.compound_dtos import (
    BioactivityDTO,
    CompoundPageRefDTO,
    CompoundProfileDTO,
)

if TYPE_CHECKING:
    from application.ports.compound_vector_store import CompoundVectorStore
    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.repositories.page_read_models import PageReadModel
    from application.ports.repositories.tag_dictionary_read_model import TagDictionaryReadModel

logger = structlog.get_logger()


class GetCompoundProfileUseCase:
    """Structure + workspace-wide activity profile for a compound, looked up by name.

    Composes the compound structure store (SMILES) with the NER bioactivity data
    aggregated across the workspace's documents (tag_dictionary + page tag_mentions),
    ACL-filtered. Unknown names return an empty profile (has_structure=False), never 404.
    """

    def __init__(
        self,
        tag_dictionary: TagDictionaryReadModel,
        page_read_model: PageReadModel,
        artifact_read_model: ArtifactReadModel,
        compound_vector_store: CompoundVectorStore,
    ) -> None:
        self._tag_dict = tag_dictionary
        self._pages = page_read_model
        self._artifacts = artifact_read_model
        self._compounds = compound_vector_store

    async def execute(
        self,
        name: str,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> CompoundProfileDTO:
        name = (name or "").strip()
        if not name:
            return CompoundProfileDTO(name="", has_structure=False)

        structures = await self._compounds.get_compounds_by_extracted_id(
            extracted_id=name,
            workspace_id=workspace_id,
            allowed_artifact_ids=allowed_artifact_ids,
        )
        canonical_smiles = extracted_id = None
        if structures:
            canonical_smiles = structures[0].canonical_smiles or structures[0].smiles
            extracted_id = structures[0].extracted_id

        bioactivities, synonyms, refs = await self._collect_activity(
            name, workspace_id, allowed_artifact_ids,
        )

        return CompoundProfileDTO(
            name=name,
            extracted_id=extracted_id,
            canonical_smiles=canonical_smiles,
            has_structure=bool(structures),
            synonyms=synonyms,
            bioactivities=bioactivities,
            reference_pages=refs,
        )

    async def _collect_activity(
        self,
        name: str,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> tuple[list[BioactivityDTO], list[str], list[CompoundPageRefDTO]]:
        artifact_ids = await self._tag_dict.get_artifact_ids_for_tag(
            name, entity_type="compound_name", workspace_id=workspace_id,
        )
        if not artifact_ids:
            return [], [], []
        matched = set(artifact_ids)
        if allowed_artifact_ids:
            matched &= {str(a) for a in allowed_artifact_ids}
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
                    "compound_profile.artifact_lookup_failed", artifact_id=str(aid), exc_info=True,
                )

        pages = await self._pages.get_pages_by_artifact_ids(matched_uuids, workspace_id=workspace_id)

        seen: set[tuple[str, str, str]] = set()
        bioactivities: list[BioactivityDTO] = []
        synonyms: set[str] = set()
        refs: list[CompoundPageRefDTO] = []
        lname = name.lower()
        for page in pages:
            page_has = False
            for tm in page.tag_mentions:
                if tm.entity_type == "compound_name" and tm.tag.lower() == lname:
                    page_has = True
                    params = tm.additional_model_params or {}
                    for bio in params.get("bioactivities") or []:
                        key = (bio.get("assay_type", ""), bio.get("value", ""), bio.get("unit", ""))
                        if key in seen:
                            continue
                        seen.add(key)
                        bioactivities.append(
                            BioactivityDTO(
                                assay_type=bio.get("assay_type", ""),
                                value=bio.get("value", ""),
                                unit=bio.get("unit") or None,
                                raw_text=bio.get("raw_text") or None,
                            ),
                        )
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
        return bioactivities, sorted(synonyms), refs
