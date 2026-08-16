"""Trigger resource registration with the permission system.

Called by the pipeline worker when an Artifact.Created event is received.
Registers the artifact as a resource in Duar so entity-level permissions
(sharing, visibility) can be applied.
"""

from uuid import UUID

import structlog

from application.ports.permission_registrar import PermissionRegistrar

logger = structlog.get_logger()


class TriggerResourceRegistrationUseCase:
    def __init__(self, permission_registrar: PermissionRegistrar) -> None:
        self._registrar = permission_registrar

    async def execute(
        self,
        resource_type: str,
        resource_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
    ) -> None:
        await self._registrar.register_resource(
            resource_type=resource_type,
            resource_id=resource_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
        )
