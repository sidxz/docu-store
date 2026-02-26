from collections.abc import Callable
from uuid import UUID

import structlog
from returns.result import Success
from temporalio import activity

from application.use_cases.smiles_embedding_use_cases import EmbedCompoundSmilesUseCase

logger = structlog.get_logger()


def create_embed_compound_smiles_activity(
    use_case: EmbedCompoundSmilesUseCase,
) -> Callable[[str], dict]:
    """Create the embed_compound_smiles activity with injected dependencies."""

    @activity.defn(name="embed_compound_smiles")
    async def embed_compound_smiles_activity(page_id: str) -> dict:
        logger.info("embed_compound_smiles_activity_start", page_id=page_id)

        try:
            page_uuid = UUID(page_id)
            result = await use_case.execute(page_id=page_uuid)
        except Exception as e:
            logger.exception(
                "embed_compound_smiles_activity_exception",
                page_id=page_id,
                error=str(e),
            )
            raise
        else:
            if isinstance(result, Success):
                dto = result.unwrap()
                logger.info(
                    "embed_compound_smiles_activity_success",
                    page_id=page_id,
                    embedded=dto.embedded_count,
                    skipped=dto.skipped_count,
                )
                return {
                    "status": "success",
                    "page_id": page_id,
                    "embedded_count": dto.embedded_count,
                    "skipped_count": dto.skipped_count,
                    "model_name": dto.model_name,
                }

            error = result.failure()
            logger.error(
                "embed_compound_smiles_activity_failed",
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

    return embed_compound_smiles_activity
