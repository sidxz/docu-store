from uuid import UUID

import structlog
from fastapi import HTTPException, status
from lagom import Container
from sentinel_auth import RequestAuth

from application.dtos.artifact_dtos import ArtifactResponse
from application.dtos.errors import AppError
from application.dtos.page_dtos import PageResponse
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.page_read_models import PageReadModel

logger = structlog.get_logger()


def _map_app_error_to_http_exception(error: AppError) -> HTTPException:
    """Map application layer errors to appropriate HTTP exceptions."""
    if error.category == "validation":
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error.message,
        )
    if error.category == "not_found":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error.message,
        )
    if error.category == "forbidden":
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error.message,
        )
    if error.category == "unauthorized":
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error.message,
        )
    if error.category == "concurrency":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error.message,
        )
    # Unknown error category
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
    )


async def get_allowed_artifact_ids(auth: RequestAuth) -> list[UUID] | None:
    """Get artifact IDs the user can access, or None for full access.

    Calls Sentinel's accessible() endpoint. Returns None (no filtering)
    when the user has full access or when Sentinel is unavailable (graceful
    degradation to workspace-only filtering).
    """
    try:
        ids, has_full_access = await auth.accessible("artifact", "view")
        if has_full_access:
            return None
        return ids
    except Exception:
        logger.warning("permission_accessible_failed", exc_info=True)
        return None


async def require_workspace_artifact(
    artifact_id: UUID, auth: RequestAuth, container: Container
) -> ArtifactResponse:
    """Load artifact from read model, raise 404 if missing or wrong workspace."""
    repo = container[ArtifactReadModel]
    artifact = await repo.get_artifact_by_id(artifact_id)
    if artifact is None or (
        artifact.workspace_id is not None
        and artifact.workspace_id != auth.workspace_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found"
        )
    return artifact


async def require_artifact_permission(
    artifact_id: UUID, auth: RequestAuth, action: str = "view",
) -> None:
    """Check entity-level permission on an artifact, raise 403 if denied."""
    allowed = await auth.can("artifact", artifact_id, action)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this artifact",
        )


async def require_page_permission(
    page: PageResponse, auth: RequestAuth, action: str = "view",
) -> None:
    """Check page permission via its parent artifact."""
    await require_artifact_permission(page.artifact_id, auth, action)


async def require_workspace_page(
    page_id: UUID, auth: RequestAuth, container: Container
) -> PageResponse:
    """Load page from read model, raise 404 if missing or wrong workspace."""
    repo = container[PageReadModel]
    page = await repo.get_page_by_id(page_id)
    if page is None or (
        page.workspace_id is not None
        and page.workspace_id != auth.workspace_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found"
        )
    return page
