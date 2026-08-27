"""Caching decorator for WorkflowOrchestrator.

Wraps any WorkflowOrchestrator implementation with a cache-aside pattern:
live results are written through to the cache; NOT_FOUND results fall back
to cached status. All non-status methods are delegated transparently.

This keeps the Temporal adapter (TemporalWorkflowOrchestrator) as a pure
single-responsibility adapter while isolating the caching concern here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from infrastructure.temporal.orchestrator import pipeline_workflow_ids

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.workflow_dtos import TemporalWorkflowInfo
    from application.ports.workflow_orchestrator import WorkflowOrchestrator
    from application.ports.workflow_status_cache import WorkflowStatusCache

logger = structlog.get_logger()


_TERMINAL = frozenset({"COMPLETED", "FAILED", "TIMED_OUT", "TERMINATED", "CANCELED"})


class CachingWorkflowOrchestrator:
    """Decorator that adds status caching to any WorkflowOrchestrator.

    Overrides only the two status-query methods. All other methods
    (start_*, etc.) are delegated to the inner orchestrator via __getattr__.
    """

    def __init__(
        self,
        inner: WorkflowOrchestrator,
        cache: WorkflowStatusCache,
    ) -> None:
        self._inner = inner
        self._cache = cache

    def __getattr__(self, name: str) -> Any:
        """Delegate all non-overridden methods to the inner orchestrator."""
        return getattr(self._inner, name)

    async def get_page_workflow_statuses(
        self,
        page_id: UUID,
    ) -> dict[str, TemporalWorkflowInfo]:
        results = await self._inner.get_page_workflow_statuses(page_id)
        return await self._apply_cache(results, str(page_id), "page")

    async def get_artifact_workflow_statuses(
        self,
        artifact_id: UUID,
    ) -> dict[str, TemporalWorkflowInfo]:
        results = await self._inner.get_artifact_workflow_statuses(artifact_id)
        return await self._apply_cache(results, str(artifact_id), "artifact")

    async def get_workflow_statuses(
        self,
        workflow_ids: dict[str, str],
    ) -> dict[str, TemporalWorkflowInfo]:
        return await self._inner.get_workflow_statuses(workflow_ids)

    async def get_artifact_pipeline_statuses(
        self,
        artifact_id: UUID,
        page_ids: list[UUID],
    ) -> dict[str, TemporalWorkflowInfo]:
        """Cache-first: terminal statuses come from Mongo, only the rest hit Temporal.

        Polled every few seconds by the topbar badge, so a 40-page deck must not
        cost ~300 describes per poll once its workflows have finished.
        """
        ids = pipeline_workflow_ids(artifact_id, page_ids)
        results: dict[str, TemporalWorkflowInfo] = {}
        try:
            cached = await self._cache.get_cached_statuses(ids)
        except Exception:
            logger.warning("workflow_status_cache_read_failed", exc_info=True)
            cached = {}
        results.update({n: i for n, i in cached.items() if i.status in _TERMINAL})
        remaining = {n: wid for n, wid in ids.items() if n not in results}
        if remaining:
            live = await self._inner.get_workflow_statuses(remaining)
            results.update(await self._apply_cache(live, str(artifact_id), "artifact"))
        return results

    async def _apply_cache(
        self,
        results: dict[str, TemporalWorkflowInfo],
        entity_id: str,
        entity_type: str,
    ) -> dict[str, TemporalWorkflowInfo]:
        """Write-through live results; replace NOT_FOUND with cached status."""
        live_entries = [
            (name, entity_id, entity_type, info)
            for name, info in results.items()
            if info.status not in ("NOT_FOUND", "UNKNOWN")
        ]
        not_found = {
            name: info.workflow_id for name, info in results.items() if info.status == "NOT_FOUND"
        }

        # Write-through: cache live statuses
        if live_entries:
            try:
                await self._cache.bulk_upsert_statuses(live_entries)
            except Exception:
                logger.warning("workflow_status_cache_write_failed", exc_info=True)

        # Read-fallback: replace NOT_FOUND with cached values
        if not_found:
            try:
                cached = await self._cache.get_cached_statuses(not_found)
                for name, cached_info in cached.items():
                    results[name] = cached_info
            except Exception:
                logger.warning("workflow_status_cache_read_failed", exc_info=True)

        return results
