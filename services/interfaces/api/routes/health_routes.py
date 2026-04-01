"""System health and admin action routes."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from lagom import Container
from sentinel_auth import RequestAuth

from application.dtos.health_dtos import (
    BulkReEmbedRequest,
    BulkWorkflowResponse,
    DetailedHealthResponse,
)
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
    body: BulkReEmbedRequest | None = None,
) -> BulkWorkflowResponse:
    """Trigger batch re-embedding for ALL artifacts (admin only).

    Accepts an optional request body with ``targets`` to select which
    vector collections to re-embed.  When omitted, all collections
    (text, smiles, summaries) are re-embedded.
    """
    if not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    targets = body.targets if body else None
    use_case = container[TriggerBulkReEmbedUseCase]
    return await use_case.execute(workspace_id=auth.workspace_id, targets=targets)
