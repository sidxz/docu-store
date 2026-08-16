from typing import Annotated

from fastapi import APIRouter, Depends, status
from lagom import Container
from duar_auth import RequestAuth

from application.dtos.dashboard_dtos import DashboardStatsResponse
from application.ports.repositories.dashboard_read_models import DashboardReadModel
from interfaces.api.routes.helpers import get_allowed_artifact_ids
from interfaces.dependencies import get_auth, get_container

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", status_code=status.HTTP_200_OK)
async def get_dashboard_stats(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> DashboardStatsResponse:
    """Aggregate workspace statistics for the dashboard."""
    allowed_artifact_ids = await get_allowed_artifact_ids(auth)
    read_model = container[DashboardReadModel]
    return await read_model.get_dashboard_stats(
        workspace_id=auth.workspace_id,
        allowed_artifact_ids=allowed_artifact_ids,
    )
