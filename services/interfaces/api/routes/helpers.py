from fastapi import HTTPException, status

from application.dtos.errors import AppError


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
