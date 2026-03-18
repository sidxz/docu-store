"""MongoDB storage for PubChem enrichment data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from plugins.pubchem_enrichment.infrastructure.pubchem_client import PubChemCompoundInfo

logger = structlog.get_logger()

COLLECTION_NAME = "pubchem_enrichments"


class PubChemEnrichmentStore:
    """Read/write PubChem enrichment records in MongoDB."""

    def __init__(self, mongo_db: Any) -> None:
        self._collection = mongo_db[COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient queries."""
        await self._collection.create_index(
            [("canonical_smiles", 1), ("page_id", 1)],
            unique=True,
        )
        await self._collection.create_index("page_id")
        await self._collection.create_index("artifact_id")
        await self._collection.create_index("pubchem_cid")

    async def upsert_enrichment(
        self,
        page_id: UUID,
        artifact_id: UUID,
        workspace_id: UUID | None,
        info: PubChemCompoundInfo,
    ) -> None:
        """Upsert a single PubChem enrichment record."""
        doc = {
            "page_id": str(page_id),
            "artifact_id": str(artifact_id),
            "workspace_id": str(workspace_id) if workspace_id else None,
            "canonical_smiles": info.canonical_smiles,
            "pubchem_cid": info.pubchem_cid,
            "iupac_name": info.iupac_name,
            "molecular_formula": info.molecular_formula,
            "molecular_weight": info.molecular_weight,
            "inchi": info.inchi,
            "inchi_key": info.inchi_key,
            "status": info.status,
            "error_message": info.error_message,
            "enriched_at": datetime.now(UTC),
            "plugin_version": "1.0.0",
        }

        await self._collection.update_one(
            {"canonical_smiles": info.canonical_smiles, "page_id": str(page_id)},
            {"$set": doc},
            upsert=True,
        )

    async def get_enrichments_for_page(self, page_id: UUID) -> list[dict[str, Any]]:
        """Return all enrichment records for a page."""
        cursor = self._collection.find(
            {"page_id": str(page_id)},
            {"_id": 0},
        )
        return await cursor.to_list(length=None)

    async def get_enrichment_by_smiles(self, canonical_smiles: str) -> list[dict[str, Any]]:
        """Return all enrichment records for a SMILES across all pages."""
        cursor = self._collection.find(
            {"canonical_smiles": canonical_smiles},
            {"_id": 0},
        )
        return await cursor.to_list(length=None)

    async def delete_for_artifact(self, artifact_id: UUID) -> int:
        """Delete all enrichment records for an artifact. Returns deleted count."""
        result = await self._collection.delete_many({"artifact_id": str(artifact_id)})
        logger.info(
            "pubchem_enrichments_deleted_for_artifact",
            artifact_id=str(artifact_id),
            deleted_count=result.deleted_count,
        )
        return result.deleted_count

    async def delete_for_page(self, page_id: UUID) -> int:
        """Delete all enrichment records for a page. Returns deleted count."""
        result = await self._collection.delete_many({"page_id": str(page_id)})
        logger.info(
            "pubchem_enrichments_deleted_for_page",
            page_id=str(page_id),
            deleted_count=result.deleted_count,
        )
        return result.deleted_count
