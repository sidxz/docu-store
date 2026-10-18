"""Port for system-wide health checking."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from application.dtos.health_dtos import DetailedHealthResponse

if TYPE_CHECKING:
    from uuid import UUID


class SystemHealthChecker(Protocol):
    """Checks health of all infrastructure dependencies, ML models, and GPU state.

    Infrastructure adapters implement this to probe concrete services
    (MongoDB, Qdrant, Temporal, etc.) while keeping the application layer
    free of infrastructure knowledge.
    """

    async def run_checks(self, workspace_id: UUID | None = None) -> DetailedHealthResponse:
        """``workspace_id``: whose AI provider to check when workspaces bring their own keys."""
        ...
