"""Port for caching last-known Temporal workflow statuses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from application.dtos.workflow_dtos import TemporalWorkflowInfo


@runtime_checkable
class WorkflowStatusCache(Protocol):
    """Cache for persisting workflow statuses beyond Temporal retention."""

    async def get_cached_statuses(
        self,
        workflow_ids: dict[str, str],
    ) -> dict[str, TemporalWorkflowInfo]:
        """Batch-lookup cached statuses.

        Args:
            workflow_ids: Mapping of workflow_name -> temporal_workflow_id

        Returns:
            Mapping of workflow_name -> cached TemporalWorkflowInfo (with from_cache=True).
            Only includes entries found in cache.

        """
        ...

    async def delete_statuses(self, workflow_ids: list[str]) -> None:
        """Forget cached entries — called when a workflow id is (re)started, since
        Temporal reuses ids and a cached terminal status must not outlive a restart.
        """
        ...

    async def bulk_upsert_statuses(
        self,
        entries: list[tuple[str, str, str, TemporalWorkflowInfo]],
    ) -> None:
        """Batch-upsert live statuses into cache.

        Args:
            entries: List of (workflow_name, entity_id, entity_type, info) tuples.

        """
        ...
