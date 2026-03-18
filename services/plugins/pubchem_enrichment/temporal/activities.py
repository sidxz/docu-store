"""Temporal activities for PubChem enrichment."""

from __future__ import annotations

import json
from typing import Any

from temporalio import activity

from plugins.pubchem_enrichment.config import PubChemPluginSettings
from plugins.pubchem_enrichment.infrastructure.pubchem_client import PubChemClient
from plugins.pubchem_enrichment.storage.enrichment_store import PubChemEnrichmentStore
from plugins.pubchem_enrichment.use_cases.enrich_compounds import enrich_compounds_for_page


def create_enrich_activity(mongo_db: Any) -> Any:
    """Factory that creates the enrich activity with injected dependencies."""
    plugin_settings = PubChemPluginSettings()

    pubchem_client = PubChemClient(
        base_url=plugin_settings.api_base_url,
        rate_limit_per_second=plugin_settings.rate_limit_per_second,
        timeout_seconds=plugin_settings.timeout_seconds,
    )
    enrichment_store = PubChemEnrichmentStore(mongo_db)

    @activity.defn(name="enrich_compounds_from_pubchem")
    async def enrich_compounds_from_pubchem(page_data_json: str) -> dict:
        """Activity: enrich compounds for a page with PubChem data."""
        page_data = json.loads(page_data_json)
        return await enrich_compounds_for_page(
            page_data=page_data,
            pubchem_client=pubchem_client,
            enrichment_store=enrichment_store,
        )

    return enrich_compounds_from_pubchem
