from typing import Protocol
from uuid import UUID


class PermissionRegistrar(Protocol):
    """Port for registering resources with the permission system.

    Used by the pipeline worker (no user context) to register artifacts
    as Sentinel resources on creation. Uses service-key auth internally.
    """

    async def register_resource(
        self,
        resource_type: str,
        resource_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        visibility: str = "workspace",
    ) -> None: ...

    async def deregister_resource(
        self,
        resource_type: str,
        resource_id: UUID,
    ) -> None: ...
