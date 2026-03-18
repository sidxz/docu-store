"""Temporal workflow for PubChem enrichment."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    pass


@workflow.defn
class PubChemEnrichmentWorkflow:
    """Enrich compounds for a page with PubChem data.

    Receives the full page data dict (from the Kafka message) and
    runs the enrichment activity.
    """

    @workflow.run
    async def run(self, page_data_json: str) -> dict:
        """Execute the enrichment activity."""
        return await workflow.execute_activity(
            "enrich_compounds_from_pubchem",
            page_data_json,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
            ),
        )
