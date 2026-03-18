"""PubChem enrichment plugin implementation."""

from __future__ import annotations

import json
from typing import Any

import structlog

from application.plugins.manifest import PluginManifest
from plugins.pubchem_enrichment.manifest import PUBCHEM_MANIFEST

logger = structlog.get_logger()


class PubChemEventHandler:
    """Handles CompoundMentionsUpdated events and deletion cleanup."""

    def __init__(self, temporal_client: Any, task_queue: str, mongo_db: Any) -> None:
        self._temporal_client = temporal_client
        self._task_queue = task_queue
        self._mongo_db = mongo_db

    @property
    def plugin_name(self) -> str:
        return "pubchem_enrichment"

    async def handle(self, event_type: str, sub_type: str, data: dict[str, Any]) -> None:
        """Route events to enrichment workflows or deletion cleanup."""
        if event_type in ("ArtifactDeleted", "PageDeleted"):
            await self._handle_deletion(event_type, data)
            return

        await self._handle_enrichment(data)

    async def _handle_enrichment(self, data: dict[str, Any]) -> None:
        """Start PubChemEnrichmentWorkflow for the page."""
        page_id = data.get("page_id", "unknown")

        if self._temporal_client is None:
            logger.warning("pubchem_handler.no_temporal_client", page_id=page_id)
            return

        workflow_id = f"pubchem-enrichment-{page_id}"
        page_data_json = json.dumps(data)

        await self._temporal_client.start_workflow(
            "PubChemEnrichmentWorkflow",
            page_data_json,
            id=workflow_id,
            task_queue=self._task_queue,
        )

        logger.info(
            "pubchem_handler.workflow_started",
            workflow_id=workflow_id,
            page_id=page_id,
        )

    async def _handle_deletion(self, event_type: str, data: dict[str, Any]) -> None:
        """Clean up enrichment records when artifacts or pages are deleted."""
        from uuid import UUID  # noqa: PLC0415

        from plugins.pubchem_enrichment.storage.enrichment_store import (  # noqa: PLC0415
            PubChemEnrichmentStore,
        )

        if self._mongo_db is None:
            logger.warning("pubchem_handler.no_mongo_db_for_cleanup", event_type=event_type)
            return

        store = PubChemEnrichmentStore(self._mongo_db)

        if event_type == "ArtifactDeleted":
            artifact_id = data.get("artifact_id")
            if artifact_id:
                await store.delete_for_artifact(UUID(artifact_id))
        elif event_type == "PageDeleted":
            page_id = data.get("page_id")
            if page_id:
                await store.delete_for_page(UUID(page_id))


class PubChemEnrichmentPlugin:
    """Plugin implementation for PubChem compound enrichment."""

    @staticmethod
    def manifest() -> PluginManifest:
        return PUBCHEM_MANIFEST

    def create_event_handler(self, context: Any) -> PubChemEventHandler:
        return PubChemEventHandler(
            temporal_client=context.temporal_client,
            task_queue=PUBCHEM_MANIFEST.effective_task_queue(),
            mongo_db=context.mongo_db,
        )

    def create_workflows(self) -> list[type]:
        from plugins.pubchem_enrichment.temporal.workflows import (  # noqa: PLC0415
            PubChemEnrichmentWorkflow,
        )

        return [PubChemEnrichmentWorkflow]

    def create_activities(self, context: Any) -> list[Any]:
        from plugins.pubchem_enrichment.temporal.activities import (  # noqa: PLC0415
            create_enrich_activity,
        )

        return [create_enrich_activity(context.mongo_db)]

    def create_router(self, context: Any) -> Any:
        from plugins.pubchem_enrichment.api.routes import router  # noqa: PLC0415

        return router

    async def health_check(self) -> dict[str, Any]:
        return {"plugin": "pubchem_enrichment", "status": "healthy"}

    async def backfill(self, context: Any) -> None:
        """Backfill enrichment data from existing page read models.

        Iterates all pages with compound_mentions and runs the
        enrichment logic for any that don't have PubChem data yet.
        """
        logger.info("pubchem_backfill.start")

        if context.page_read_model is None or context.mongo_db is None:
            logger.warning("pubchem_backfill.missing_context")
            return

        from plugins.pubchem_enrichment.config import PubChemPluginSettings  # noqa: PLC0415
        from plugins.pubchem_enrichment.infrastructure.pubchem_client import (  # noqa: PLC0415
            PubChemClient,
        )
        from plugins.pubchem_enrichment.storage.enrichment_store import (  # noqa: PLC0415
            PubChemEnrichmentStore,
        )
        from plugins.pubchem_enrichment.use_cases.enrich_compounds import (  # noqa: PLC0415
            enrich_compounds_for_page,
        )

        plugin_settings = PubChemPluginSettings()
        pubchem_client = PubChemClient(
            base_url=plugin_settings.api_base_url,
            rate_limit_per_second=plugin_settings.rate_limit_per_second,
            timeout_seconds=plugin_settings.timeout_seconds,
        )
        enrichment_store = PubChemEnrichmentStore(context.mongo_db)
        await enrichment_store.ensure_indexes()

        pages = await context.page_read_model.find_pages_with_compounds()
        enriched = 0
        for page_data in pages:
            try:
                result = await enrich_compounds_for_page(
                    page_data=page_data,
                    pubchem_client=pubchem_client,
                    enrichment_store=enrichment_store,
                )
                enriched += result.get("enriched", 0)
            except Exception:
                logger.exception(
                    "pubchem_backfill.page_error",
                    page_id=page_data.get("page_id"),
                )

        logger.info("pubchem_backfill.complete", enriched=enriched)
