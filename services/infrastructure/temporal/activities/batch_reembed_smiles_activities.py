"""Temporal activity for batch re-embedding compound SMILES vectors."""

from collections.abc import Callable
from uuid import UUID

import structlog
from temporalio import activity

from application.use_cases.batch_reembed_use_cases import BatchReEmbedSmilesUseCase

logger = structlog.get_logger()


def create_batch_reembed_smiles_activity(
    use_case: BatchReEmbedSmilesUseCase,
) -> Callable[[str], dict]:
    """Create the batch_reembed_smiles activity with injected dependencies."""

    @activity.defn(name="batch_reembed_smiles")
    async def batch_reembed_smiles_activity(artifact_id: str) -> dict:
        logger.info("batch_reembed_smiles_activity_start", artifact_id=artifact_id)

        try:
            result = await use_case.execute(artifact_id=UUID(artifact_id))
        except Exception as e:
            logger.exception(
                "batch_reembed_smiles_activity_exception",
                artifact_id=artifact_id,
                error=str(e),
            )
            raise
        else:
            logger.info(
                "batch_reembed_smiles_activity_complete",
                artifact_id=artifact_id,
                status=result.get("status"),
                compound_count=result.get("compound_count", 0),
            )
            return result

    return batch_reembed_smiles_activity
