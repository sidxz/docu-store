from uuid import UUID

import structlog
from fastapi import HTTPException, status
from lagom import Container
from returns.result import Failure
from duar_auth import RequestAuth

from application.dtos.artifact_dtos import ArtifactResponse
from application.dtos.errors import AppError
from application.dtos.page_dtos import PageResponse
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.page_read_models import PageReadModel

logger = structlog.get_logger()


def _map_app_error_to_http_exception(error: AppError) -> HTTPException:  # noqa: PLR0911 — one branch per error category, a dispatch table would be less readable
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
    if error.category == "rate_limited":
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error.message,
        )
    # Unknown error category
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
    )


async def get_allowed_artifact_ids(auth: RequestAuth) -> list[UUID] | None:
    """Get artifact IDs the user can access, or None for full access.

    Calls Duar's accessible() endpoint. Returns None (no filtering)
    when the user has full access or when Duar is unavailable (graceful
    degradation to workspace-only filtering).
    """
    try:
        ids, has_full_access = await auth.accessible("artifact", "view")
    except Exception:
        logger.warning("permission_accessible_failed", exc_info=True)
        return None
    else:
        if has_full_access:
            return None
        return ids


async def require_workspace_artifact(
    artifact_id: UUID,
    auth: RequestAuth,
    container: Container,
) -> ArtifactResponse:
    """Load artifact from read model, raise 404 if missing or wrong workspace."""
    repo = container[ArtifactReadModel]
    # Scope the query itself: a doc in another workspace (or with no workspace_id)
    # simply won't match, so it can't leak by knowing the id.
    artifact = await repo.get_artifact_by_id(artifact_id, workspace_id=auth.workspace_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return artifact


async def require_action(auth: RequestAuth, action: str) -> None:
    """Check workspace RBAC action, raise 403 if the user's roles don't grant it.

    Workspace admins/owners bypass, mirroring entity-level resolution (see
    Duar check_permission); without this, a fresh workspace has no role
    granting any action and every member would be locked out.
    """
    if auth.is_admin:
        return
    if not await auth.check_action(action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to perform this action ({action})",
        )


async def require_artifact_permission(
    artifact_id: UUID,
    auth: RequestAuth,
    action: str = "view",
) -> None:
    """Check entity-level permission on an artifact, raise 403 if denied."""
    allowed = await auth.can("artifact", artifact_id, action)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this artifact",
        )


async def require_page_permission(
    page: PageResponse,
    auth: RequestAuth,
    action: str = "view",
) -> None:
    """Check page permission via its parent artifact."""
    await require_artifact_permission(page.artifact_id, auth, action)


async def require_workspace_page(
    page_id: UUID,
    auth: RequestAuth,
    container: Container,
) -> PageResponse:
    """Load page from read model, raise 404 if missing or wrong workspace."""
    repo = container[PageReadModel]
    page = await repo.get_page_by_id(page_id, workspace_id=auth.workspace_id)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return page


async def ensure_within_quota(auth: RequestAuth, container: Container) -> None:
    """Pre-flight monthly token quota gate (chat send + upload/create).

    Admins are exempt. Raises 429 with a human-readable detail when the
    caller is over their effective monthly limit; the check itself fails
    open on infrastructure errors (see CheckTokenQuotaUseCase).
    """
    if auth.is_admin:
        return
    from application.use_cases.token_limit_use_cases import CheckTokenQuotaUseCase

    result = await container[CheckTokenQuotaUseCase].execute(auth.workspace_id, auth.user_id)
    if isinstance(result, Failure):
        raise _map_app_error_to_http_exception(result.failure())


LLM_NOT_CONFIGURED_DETAIL = (
    "Add an LLM provider in Settings → AI Provider before uploading or chatting."
)


async def ensure_llm_configured(auth: RequestAuth, container: Container) -> None:
    """Pre-flight BYO-key gate (chat send + upload/create).

    Raises 428 before any blob write or event when this caller has no LLM to
    bill. No-op when USER_LLM_KEYS_ENABLED is off or the env defaults can serve
    the call. 428, not 409 — the chat client treats 409 on send as "a run is
    already active → reattach".
    """
    from application.ports.user_llm_config import UserLLMConfigStore
    from infrastructure.config import Settings
    from infrastructure.llm.factory import server_llm_available

    settings = container[Settings]
    if not settings.user_llm_keys_enabled or server_llm_available(settings):
        return
    store = container[UserLLMConfigStore]
    if await store.get_entry(auth.workspace_id, auth.user_id) is not None:
        return
    raise HTTPException(
        status_code=status.HTTP_428_PRECONDITION_REQUIRED,
        detail=LLM_NOT_CONFIGURED_DETAIL,
    )
