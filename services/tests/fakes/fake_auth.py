"""Fake auth context for testing."""

from __future__ import annotations

from uuid import UUID, uuid4

_ROLE_HIERARCHY = {"viewer": 0, "editor": 1, "admin": 2, "owner": 3}


class FakeAuth:
    """Satisfies the AuthContext Protocol for unit tests."""

    def __init__(
        self,
        role: str = "editor",
        user_id: UUID | None = None,
        workspace_id: UUID | None = None,
    ) -> None:
        self.user_id = user_id or uuid4()
        self.workspace_id = workspace_id or uuid4()
        self.workspace_role = role
        self.is_admin = role in ("admin", "owner")

    def has_role(self, minimum_role: str) -> bool:
        return _ROLE_HIERARCHY.get(self.workspace_role, -1) >= _ROLE_HIERARCHY.get(
            minimum_role,
            99,
        )

    async def can(
        self,
        resource_type: str,
        resource_id: UUID,
        action: str,
    ) -> bool:
        """Return True by default in tests (full access)."""
        return True

    async def accessible(
        self,
        resource_type: str,
        action: str,
        limit: int | None = None,
    ) -> tuple[list[UUID], bool]:
        """Return full access by default in tests."""
        return ([], True)

    async def share(
        self,
        resource_type: str,
        resource_id: UUID,
        grantee_type: str,
        grantee_id: UUID,
        permission: str = "view",
    ) -> dict:
        return {"status": "ok"}

    async def unshare(
        self,
        resource_type: str,
        resource_id: UUID,
        grantee_type: str,
        grantee_id: UUID,
        permission: str = "view",
    ) -> dict:
        return {"status": "ok"}

    async def update_visibility(
        self,
        resource_type: str,
        resource_id: UUID,
        visibility: str,
    ) -> dict:
        return {"status": "ok"}

    async def get_resource_acl(
        self,
        resource_type: str,
        resource_id: UUID,
    ) -> dict:
        return {"id": str(uuid4()), "visibility": "workspace", "shares": []}

    async def get_enriched_resource_acl(
        self,
        resource_type: str,
        resource_id: UUID,
    ) -> dict:
        return {
            "id": str(uuid4()),
            "visibility": "workspace",
            "owner_id": str(self.user_id),
            "owner_name": "Test User",
            "owner_email": "test@example.com",
            "shares": [],
        }

    async def search_members(
        self,
        query: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        return []

    async def list_members(self, limit: int | None = None) -> list[dict]:
        return []

    async def list_groups(self) -> list[dict]:
        return []

    async def get_group_members(self, group_id: UUID) -> list[dict]:
        return []
