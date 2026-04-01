"""Port for system-wide health checking."""

from __future__ import annotations

from typing import Protocol

from application.dtos.health_dtos import DetailedHealthResponse


class SystemHealthChecker(Protocol):
    """Checks health of all infrastructure dependencies, ML models, and GPU state.

    Infrastructure adapters implement this to probe concrete services
    (MongoDB, Qdrant, Temporal, etc.) while keeping the application layer
    free of infrastructure knowledge.
    """

    async def run_checks(self) -> DetailedHealthResponse: ...
