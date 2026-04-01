"""Use case for retrieving comprehensive system health."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.dtos.health_dtos import DetailedHealthResponse
    from application.ports.system_health_checker import SystemHealthChecker


class GetSystemHealthUseCase:
    """Query the system health checker and return a consolidated report.

    This is an application-layer orchestrator so that interface routes
    never reach directly into infrastructure.
    """

    def __init__(self, health_checker: SystemHealthChecker) -> None:
        self._health_checker = health_checker

    async def execute(self) -> DetailedHealthResponse:
        return await self._health_checker.run_checks()
