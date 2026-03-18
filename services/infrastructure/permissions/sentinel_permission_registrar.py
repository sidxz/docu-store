from uuid import UUID

import structlog
from sentinel_auth import PermissionClient

logger = structlog.get_logger()


class SentinelPermissionRegistrar:
    """Adapter that registers resources with Sentinel's permission system.

    Uses the SDK's PermissionClient which authenticates via service key
    (no user JWT needed for registration).
    """

    def __init__(self, permission_client: PermissionClient) -> None:
        self._client = permission_client

    async def register_resource(
        self,
        resource_type: str,
        resource_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        visibility: str = "workspace",
    ) -> None:
        await self._client.register_resource(
            resource_type=resource_type,
            resource_id=resource_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            visibility=visibility,
        )
        logger.info(
            "resource_registered",
            resource_type=resource_type,
            resource_id=str(resource_id),
            workspace_id=str(workspace_id),
            owner_id=str(owner_id),
        )

    async def deregister_resource(
        self,
        resource_type: str,
        resource_id: UUID,
    ) -> None:
        await self._client.deregister_resource(
            resource_type=resource_type,
            resource_id=resource_id,
        )
        logger.info(
            "resource_deregistered",
            resource_type=resource_type,
            resource_id=str(resource_id),
        )
