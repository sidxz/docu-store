"""Temporal activity for artifact parsing."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

if TYPE_CHECKING:
    from application.use_cases.parse_artifact_use_case import ParseArtifactUseCase

logger = structlog.get_logger(__name__)


def create_parse_artifact_activity(use_case: ParseArtifactUseCase) -> Callable[[str], dict]:
    """Create the parse_artifact activity with dependencies injected."""

    @activity.defn(name="parse_artifact")
    async def parse_artifact_activity(artifact_id: str) -> dict:
        logger.info("parse_artifact_activity_start", artifact_id=artifact_id)
        result = await use_case.execute(artifact_id=UUID(artifact_id))
        if isinstance(result, Success):
            page_ids = result.unwrap()
            return {"status": "success", "artifact_id": artifact_id, "page_count": len(page_ids)}
        error = result.failure()
        # Raise so Temporal retries on transient failures.
        msg = f"{error.category}: {error.message}"
        raise RuntimeError(msg)

    return parse_artifact_activity
