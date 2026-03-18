"""Core enrichment logic — look up compounds in PubChem and store results."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from plugins.pubchem_enrichment.infrastructure.pubchem_client import PubChemClient
from plugins.pubchem_enrichment.storage.enrichment_store import PubChemEnrichmentStore

logger = structlog.get_logger()


async def enrich_compounds_for_page(
    page_data: dict[str, Any],
    pubchem_client: PubChemClient,
    enrichment_store: PubChemEnrichmentStore,
) -> dict[str, Any]:
    """Enrich all valid compounds for a page with PubChem data.

    Args:
        page_data: Full PageResponse DTO from the Kafka message.
        pubchem_client: PubChem API client.
        enrichment_store: MongoDB store for enrichment records.

    Returns:
        Summary dict with counts.

    """
    page_id = UUID(page_data["page_id"])
    artifact_id = UUID(page_data["artifact_id"])
    workspace_id = UUID(page_data["workspace_id"]) if page_data.get("workspace_id") else None

    compound_mentions = page_data.get("compound_mentions") or []

    # Filter to compounds with valid canonical SMILES
    valid_smiles = [
        cm["canonical_smiles"]
        for cm in compound_mentions
        if cm.get("canonical_smiles") and cm.get("is_smiles_valid")
    ]

    if not valid_smiles:
        logger.info("pubchem_enrich.no_valid_smiles", page_id=str(page_id))
        return {"page_id": str(page_id), "enriched": 0, "skipped": "no valid SMILES"}

    # Deduplicate within the page
    unique_smiles = list(dict.fromkeys(valid_smiles))

    logger.info(
        "pubchem_enrich.start",
        page_id=str(page_id),
        compound_count=len(unique_smiles),
    )

    results = await pubchem_client.lookup_batch(unique_smiles)

    success_count = 0
    for info in results:
        await enrichment_store.upsert_enrichment(
            page_id=page_id,
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            info=info,
        )
        if info.status == "success":
            success_count += 1

    logger.info(
        "pubchem_enrich.complete",
        page_id=str(page_id),
        total=len(results),
        success=success_count,
    )

    return {
        "page_id": str(page_id),
        "total": len(results),
        "enriched": success_count,
        "not_found": sum(1 for r in results if r.status == "not_found"),
        "errors": sum(1 for r in results if r.status == "error"),
    }
