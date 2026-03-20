"""DTOs for entity-level permission operations (sharing, visibility)."""

from uuid import UUID

from pydantic import BaseModel, Field


class ShareResourceRequest(BaseModel):
    grantee_type: str = Field(pattern=r"^(user|group)$")
    grantee_id: UUID
    permission: str = Field(default="view", pattern=r"^(view|edit)$")


class UpdateVisibilityRequest(BaseModel):
    visibility: str = Field(pattern=r"^(private|workspace)$")


# ── Response models (match sentinel-auth SDK return shapes) ──


class ResourceShareResponse(BaseModel):
    """A single share entry in a resource ACL."""

    id: str
    grantee_type: str
    grantee_id: str
    grantee_name: str | None = None
    grantee_email: str | None = None
    permission: str
    granted_by: str | None = None
    granted_by_name: str | None = None
    granted_at: str | None = None


class ResourceACLResponse(BaseModel):
    """Full ACL for a resource, with enriched user profiles."""

    id: str
    resource_type: str
    resource_id: str
    workspace_id: str
    owner_id: str | None = None
    owner_name: str | None = None
    owner_email: str | None = None
    visibility: str
    shares: list[ResourceShareResponse] = Field(default_factory=list)


class ShareActionResponse(BaseModel):
    """Response from share/unshare operations."""

    ok: bool = True
    resource_type: str
    resource_id: str
    grantee_type: str
    grantee_id: str
    permission: str


class VisibilityResponse(BaseModel):
    """Response from visibility update."""

    ok: bool = True
    resource_type: str
    resource_id: str
    visibility: str
