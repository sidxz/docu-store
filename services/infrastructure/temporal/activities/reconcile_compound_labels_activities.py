from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.reconcile_compound_labels_use_case import (
    ReconcileCompoundLabelsUseCase,
)

logger = structlog.get_logger()


def create_reconcile_compound_labels_activity(
    use_case: ReconcileCompoundLabelsUseCase,
) -> Callable[[str], dict]:
    """Create the reconcile_compound_labels activity with injected dependencies."""

    @activity.defn(name="reconcile_compound_labels")
    async def reconcile_compound_labels_activity(page_id: str) -> dict:
        logger.info("reconcile_compound_labels_activity_start", page_id=page_id)

        try:
            page_uuid = UUID(page_id)
            result = await use_case.execute(page_id=page_uuid)
        except Exception as e:
            logger.exception(
                "reconcile_compound_labels_activity_exception",
                page_id=page_id,
                error=str(e),
            )
            raise
        else:
            if isinstance(result, Success):
                dto = result.unwrap()
                logger.info(
                    "reconcile_compound_labels_activity_success",
                    page_id=page_id,
                    changed=len(dto.changes),
                    applied=dto.applied,
                )
                return {
                    "status": "success",
                    "page_id": page_id,
                    "changed": len(dto.changes),
                    "applied": dto.applied,
                }

            error = result.failure()
            logger.error(
                "reconcile_compound_labels_activity_failed",
                page_id=page_id,
                error_code=error.category,
                error_message=error.message,
            )
            return {
                "status": "failed",
                "page_id": page_id,
                "error_code": error.category,
                "error_message": error.message,
            }

    return reconcile_compound_labels_activity
