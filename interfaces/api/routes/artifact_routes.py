from collections.abc import Container
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from returns.result import Failure, Success

from application.dtos.artifact_dtos import ArtifactResponse, CreateArtifactRequest
from application.use_cases.artifact_use_cases import CreateArtifactUseCase
from domain.exceptions import InfrastructureError
from interfaces.api.routes.helpers import _map_app_error_to_http_exception
from interfaces.dependencies import get_container

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_artifact(
    request: CreateArtifactRequest,
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Create a new artifact.

    Returns:
        201 Created: Artifact successfully created
        400 Bad Request: Validation error
        500 Internal Server Error: Infrastructure failure (DB unavailable, etc.)

    """
    use_case = container[CreateArtifactUseCase]

    try:
        result = await use_case.execute(request=request)

        if isinstance(result, Success):
            return result.unwrap()

        if isinstance(result, Failure):
            raise _map_app_error_to_http_exception(result.failure()) from None

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected result type",
        ) from None
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except InfrastructureError as exc:
        # Infrastructure errors should return 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service temporarily unavailable",
        ) from exc
    except BaseException as exc:
        # Unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc
