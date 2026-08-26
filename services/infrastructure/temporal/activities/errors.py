"""Map use-case outcomes to Temporal failures.

Nothing is reported as a *completed* activity unless the work succeeded — a
failed enrichment must show as a failed workflow (the page/artifact
workflow-status endpoints read Temporal state).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from temporalio.exceptions import ApplicationError

if TYPE_CHECKING:
    from application.dtos.errors import AppError
    from domain.exceptions import LLMError

# Retrying can't fix these. Everything else (concurrency, internal_error —
# e.g. Ollama down) gets the workflow's RetryPolicy.
_NON_RETRYABLE_CATEGORIES = frozenset({"not_found", "validation", "not_ready"})


def llm_error_to_application_error(exc: LLMError) -> ApplicationError:
    return ApplicationError(str(exc), type=type(exc).__name__, non_retryable=not exc.retryable)


def failure_to_application_error(error: AppError) -> ApplicationError:
    return ApplicationError(
        error.message,
        type=error.category,
        non_retryable=error.category in _NON_RETRYABLE_CATEGORIES,
    )
