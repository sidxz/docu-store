"""Error handling middleware and decorators for API routes."""

import functools
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeVar

import structlog
from fastapi import HTTPException, status
from returns.result import Failure, Success

from domain.exceptions import InfrastructureError
from interfaces.api.routes.helpers import _map_app_error_to_http_exception

if TYPE_CHECKING:
    from typing import Any

logger = structlog.get_logger()

T = TypeVar("T")


def _raise_mapped_http_error(failure: object) -> None:
    error = _map_app_error_to_http_exception(failure)
    raise error from None


def _raise_unexpected_result_type() -> None:
    detail = "Unexpected result type"
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=detail,
    ) from None


def handle_use_case_errors[T_co](
    func: Callable[..., Awaitable[T_co]],
) -> Callable[..., Awaitable[T_co]]:
    """Handle common use case error patterns.

    This decorator centralizes error handling for use case execution:
    - Unwraps Success results
    - Maps Failure results to HTTP exceptions
    - Handles InfrastructureError
    - Catches and logs unexpected errors

    Args:
        func: An async endpoint function that executes a use case

    Returns:
        Wrapped function with centralized error handling

    """

    @functools.wraps(func)
    async def wrapper(*args: "Any", **kwargs: "Any") -> T_co:  # noqa: ANN401
        try:
            result = await func(*args, **kwargs)

            # Handle result types
            if isinstance(result, Success):
                return result.unwrap()

            if isinstance(result, Failure):
                _raise_mapped_http_error(result.failure())

            # Unexpected result type
            _raise_unexpected_result_type()

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except InfrastructureError as exc:
            logger.exception(
                "infrastructure_error",
                error=str(exc),
                function=func.__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Service temporarily unavailable",
            ) from exc
        except BaseException as exc:
            logger.exception(
                "unexpected_error",
                error=str(exc),
                error_type=type(exc).__name__,
                function=func.__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc

    return wrapper
