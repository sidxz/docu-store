"""Browse routes for tag-based document exploration."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from lagom import Container
from sentinel_auth import RequestAuth

from application.dtos.browse_dtos import (
    ArtifactBrowseItemDTO,
    BrowseCategoriesResponse,
    BrowseFoldersResponse,
)
from application.ports.repositories.tag_browse_read_model import TagBrowseReadModel
from infrastructure.config import settings
from interfaces.api.routes.helpers import (
    get_allowed_artifact_ids as _get_allowed_artifact_ids,
)
from interfaces.dependencies import get_auth, get_container

logger = structlog.get_logger()

router = APIRouter(prefix="/browse", tags=["browse"])


@router.get("/categories")
async def get_categories(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> BrowseCategoriesResponse:
    """List tag categories with artifact counts for the browse UI."""
    allowed = await _get_allowed_artifact_ids(auth)
    read_model = container[TagBrowseReadModel]
    return await read_model.get_tag_categories(
        workspace_id=auth.workspace_id,
        limit=limit,
        sticky_categories=settings.browse_sticky_categories_list,
        allowed_artifact_ids=allowed,
    )


@router.get("/categories/{entity_type}/folders")
async def get_folders(
    entity_type: str,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    parent: Annotated[str | None, Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> BrowseFoldersResponse:
    """List folders (distinct tag values) within a category."""
    allowed = await _get_allowed_artifact_ids(auth)
    read_model = container[TagBrowseReadModel]
    return await read_model.get_tag_folders(
        entity_type=entity_type,
        workspace_id=auth.workspace_id,
        parent=parent,
        skip=skip,
        limit=limit,
        allowed_artifact_ids=allowed,
    )


@router.get("/categories/{entity_type}/folders/{tag_value}/artifacts")
async def get_folder_artifacts(
    entity_type: str,
    tag_value: str,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ArtifactBrowseItemDTO]:
    """List artifacts within a specific folder."""
    allowed = await _get_allowed_artifact_ids(auth)
    read_model = container[TagBrowseReadModel]
    return await read_model.get_folder_artifacts(
        entity_type=entity_type,
        tag_value=tag_value,
        workspace_id=auth.workspace_id,
        skip=skip,
        limit=limit,
        allowed_artifact_ids=allowed,
    )
