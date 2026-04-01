"""Port for reading worker heartbeat status."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from application.dtos.health_dtos import WorkerHeartbeat


class WorkerHeartbeatStore(Protocol):
    """Read-only query port for worker heartbeat data.

    Infrastructure adapters implement this — the application layer
    never knows about MongoDB or the heartbeat collection.
    """

    async def get_all_workers(self) -> list[WorkerHeartbeat]: ...
