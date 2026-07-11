"""Compound routes — structure + activity profile lookups."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from lagom import Container
from sentinel_auth import RequestAuth

from application.dtos.compound_dtos import CompoundProfileDTO
from application.use_cases.compound_profile_use_case import GetCompoundProfileUseCase
from interfaces.api.routes.helpers import get_allowed_artifact_ids
from interfaces.dependencies import get_auth, get_container

router = APIRouter(prefix="/compounds", tags=["compounds"])


@router.get("/{name}/profile", status_code=status.HTTP_200_OK)
async def get_compound_profile(
    name: str,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> CompoundProfileDTO:
    """Structure + workspace-wide activity profile for a compound name."""
    allowed_artifact_ids = await get_allowed_artifact_ids(auth)
    use_case = container[GetCompoundProfileUseCase]
    return await use_case.execute(name, auth.workspace_id, allowed_artifact_ids)
