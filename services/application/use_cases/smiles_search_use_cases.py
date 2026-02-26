from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.dtos.smiles_embedding_dtos import (
    CompoundSearchRequest,
    CompoundSearchResponse,
    CompoundSearchResultDTO,
)

if TYPE_CHECKING:
    from application.ports.compound_vector_store import CompoundVectorStore
    from application.ports.embedding_generator import EmbeddingGenerator
    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.smiles_validator import SmilesValidator

logger = structlog.get_logger()


class SearchSimilarCompoundsUseCase:
    """Search the compound vector store for structurally similar compounds.

    Steps:
    1. Validate the query SMILES — return 400 if invalid
    2. Canonicalize to match how stored embeddings were generated
    3. Embed the canonical SMILES with ChemBERTa
    4. Query the compound Qdrant collection
    5. Enrich results with artifact metadata from the read model
    6. Return CompoundSearchResponse
    """

    def __init__(
        self,
        smiles_embedding_generator: EmbeddingGenerator,
        compound_vector_store: CompoundVectorStore,
        artifact_read_model: ArtifactReadModel,
        smiles_validator: SmilesValidator,
    ) -> None:
        self.smiles_embedding_generator = smiles_embedding_generator
        self.compound_vector_store = compound_vector_store
        self.artifact_read_model = artifact_read_model
        self.smiles_validator = smiles_validator

    async def execute(
        self,
        request: CompoundSearchRequest,
    ) -> Result[CompoundSearchResponse, AppError]:
        try:
            logger.info(
                "search_similar_compounds_start",
                query_smiles=request.query_smiles[:80],
                limit=request.limit,
            )

            # 1. Validate query SMILES
            if not self.smiles_validator.validate(request.query_smiles):
                return Failure(
                    AppError("validation", f"Invalid SMILES: {request.query_smiles!r}"),
                )

            # 2. Canonicalize — embed the same form as stored vectors
            canonical = self.smiles_validator.canonicalize(request.query_smiles)
            query_smiles_to_embed = canonical or request.query_smiles

            # 3. Generate ChemBERTa embedding
            query_embedding = await self.smiles_embedding_generator.generate_text_embedding(
                text=query_smiles_to_embed,
            )

            # 4. Vector search
            search_results = await self.compound_vector_store.search_similar_compounds(
                query_embedding=query_embedding,
                limit=request.limit,
                artifact_id_filter=request.artifact_id,
                score_threshold=request.score_threshold,
            )

            # 5. Enrich with artifact metadata
            result_dtos = []
            for result in search_results:
                artifact = await self.artifact_read_model.get_artifact_by_id(result.artifact_id)
                artifact_name = artifact.source_filename if artifact else None

                result_dtos.append(
                    CompoundSearchResultDTO(
                        smiles=result.smiles,
                        canonical_smiles=result.canonical_smiles,
                        extracted_id=result.extracted_id,
                        confidence=result.metadata.get("confidence"),
                        similarity_score=result.score,
                        page_id=result.page_id,
                        page_index=result.page_index,
                        artifact_id=result.artifact_id,
                        artifact_name=artifact_name,
                    ),
                )

            model_info = await self.smiles_embedding_generator.get_model_info()

            logger.info(
                "search_similar_compounds_success",
                results_count=len(result_dtos),
            )

            return Success(
                CompoundSearchResponse(
                    query_smiles=request.query_smiles,
                    query_canonical_smiles=canonical,
                    results=result_dtos,
                    total_results=len(result_dtos),
                    model_used=str(model_info.get("model_name", "unknown")),
                ),
            )

        except Exception as e:
            logger.exception(
                "search_similar_compounds_failed",
                query_smiles=request.query_smiles[:80],
                error=str(e),
            )
            return Failure(AppError("internal_error", f"Failed to search compounds: {e!s}"))
