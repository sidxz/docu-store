from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from application.dtos.compound_dtos import CompoundProfileDTO

if TYPE_CHECKING:
    from application.ports.compound_vector_store import CompoundVectorStore
    from application.services.compound_activity_query import CompoundActivityQuery

logger = structlog.get_logger()


class GetCompoundProfileUseCase:
    """Structure + workspace-wide activity profile for a compound, looked up by name.

    Composes the compound structure store (SMILES) with the shared bioactivity
    assembly (``CompoundActivityQuery``) aggregated across the workspace's
    documents, ACL-filtered. Unknown names return an empty profile
    (has_structure=False), never 404.
    """

    def __init__(
        self,
        activity_query: CompoundActivityQuery,
        compound_vector_store: CompoundVectorStore,
    ) -> None:
        self._activity = activity_query
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

        bioactivities, synonyms, refs = await self._activity.collect(
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
