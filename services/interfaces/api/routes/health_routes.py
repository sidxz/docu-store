"""System health and admin action routes."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from lagom import Container
from sentinel_auth import RequestAuth

from application.dtos.health_dtos import BulkWorkflowResponse, DetailedHealthResponse
from application.use_cases.system_health_use_case import GetSystemHealthUseCase
from application.workflow_use_cases.trigger_bulk_reembed_use_case import TriggerBulkReEmbedUseCase
from interfaces.dependencies import get_auth, get_container

logger = structlog.get_logger()

router = APIRouter(prefix="/system", tags=["system"])


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health", status_code=status.HTTP_200_OK)
async def get_detailed_health(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> DetailedHealthResponse:
    """Comprehensive health check for all services, models, and infrastructure (admin only)."""
    if not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    logger.info("detailed_health_check_requested")
    use_case = container[GetSystemHealthUseCase]
    return await use_case.execute()


# ---------------------------------------------------------------------------
# Admin actions
# ---------------------------------------------------------------------------


@router.post("/reembed-all", status_code=status.HTTP_202_ACCEPTED)
async def trigger_reembed_all(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> BulkWorkflowResponse:
    """Trigger batch re-embedding for ALL artifacts (admin only).

    Starts a BatchReEmbedArtifactPagesWorkflow for every artifact in the
    workspace. Each workflow re-embeds all pages with full contextual
    prefixes. Useful after fixing GPU/driver issues, updating embedding
    models, or changing enrichment config.
    """
    if not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    use_case = container[TriggerBulkReEmbedUseCase]
    return await use_case.execute(workspace_id=auth.workspace_id)
