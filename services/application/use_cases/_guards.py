"""Shared auth guards and error-handling decorator for use cases.

Eliminates the repeated auth-check + exception→Failure boilerplate
that was duplicated across every use case ``execute`` method.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Protocol

import structlog
from returns.result import Failure, Result

from application.dtos.errors import AppError
from domain.exceptions import (
    AggregateNotFoundError,
    ConcurrencyError,
    ValidationError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any, TypeVar
    from uuid import UUID

    from application.ports.auth import AuthContext

    T = TypeVar("T")

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Protocols for type-safe guards
# ---------------------------------------------------------------------------


class _HasWorkspace(Protocol):
    """Any aggregate/entity carrying an optional workspace_id."""

    workspace_id: UUID | None


# ---------------------------------------------------------------------------
# Guard exceptions — raised by guards, caught by the decorator
# ---------------------------------------------------------------------------


class _GuardError(Exception):
    """Raised by auth/workspace guards to short-circuit a use case."""

    def __init__(self, error: AppError) -> None:
        self.error = error
        super().__init__(error.message)


# ---------------------------------------------------------------------------
# Guard helpers — raise _GuardError on auth/workspace violations
# ---------------------------------------------------------------------------


def require_editor(auth: AuthContext | None) -> None:
    """Raise if *auth* is present but lacks the editor role."""
    if auth and not auth.has_role("editor"):
        raise _GuardError(AppError("forbidden", "Requires editor role"))


def require_artifact_workspace(auth: AuthContext | None, artifact: _HasWorkspace) -> None:
    """Raise if *artifact* belongs to a different workspace than *auth*."""
    if auth and artifact.workspace_id is not None and artifact.workspace_id != auth.workspace_id:
        raise _GuardError(AppError("not_found", "Artifact not found"))


def require_page_workspace(auth: AuthContext | None, page: _HasWorkspace) -> None:
    """Raise if *page* belongs to a different workspace than *auth*."""
    if auth and page.workspace_id is not None and page.workspace_id != auth.workspace_id:
        raise _GuardError(AppError("not_found", "Page not found"))


# ---------------------------------------------------------------------------
# Error-handling decorator
# ---------------------------------------------------------------------------


def handle_domain_errors[T](
    func: Callable[..., Coroutine[Any, Any, Result[T, AppError]]],
) -> Callable[..., Coroutine[Any, Any, Result[T, AppError]]]:
    """Catch domain exceptions and map them to ``Failure(AppError(...))``."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Result[T, AppError]:  # noqa: ANN401
        try:
            return await func(*args, **kwargs)
        except _GuardError as e:
            return Failure(e.error)
        except AggregateNotFoundError as e:
            return Failure(AppError("not_found", str(e)))
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
        except ValueError as e:
            return Failure(AppError("invalid_operation", str(e)))

    return wrapper
