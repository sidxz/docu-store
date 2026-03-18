"""PubChem plugin API routes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from infrastructure.config import settings

router = APIRouter()


def _get_collection() -> Any:
    """Get the pubchem_enrichments MongoDB collection."""
    from motor.motor_asyncio import AsyncIOMotorClient  # noqa: PLC0415

    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db]
    return db["pubchem_enrichments"]


@router.get("/pages/{page_id}/enrichments")
async def get_enrichments_for_page(page_id: UUID) -> list[dict[str, Any]]:
    """Return all PubChem enrichment records for a page."""
    collection = _get_collection()
    cursor = collection.find({"page_id": str(page_id)}, {"_id": 0})
    return await cursor.to_list(length=None)


@router.get("/compounds/{canonical_smiles:path}")
async def get_enrichment_by_smiles(canonical_smiles: str) -> list[dict[str, Any]]:
    """Return PubChem enrichment records for a specific SMILES."""
    collection = _get_collection()
    cursor = collection.find({"canonical_smiles": canonical_smiles}, {"_id": 0})
    results = await cursor.to_list(length=None)
    if not results:
        raise HTTPException(status_code=404, detail="No enrichment found for this SMILES")
    return results


@router.get("/status")
async def plugin_status() -> dict[str, Any]:
    """Plugin health check."""
    collection = _get_collection()
    count = await collection.count_documents({})
    return {
        "plugin": "pubchem_enrichment",
        "status": "healthy",
        "total_enrichments": count,
    }
