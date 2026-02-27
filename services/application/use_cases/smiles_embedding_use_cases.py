from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.dtos.smiles_embedding_dtos import SmilesEmbeddingDTO
from domain.exceptions import AggregateNotFoundError
from domain.value_objects.embedding_metadata import EmbeddingMetadata

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.compound_vector_store import CompoundVectorStore
    from application.ports.embedding_generator import EmbeddingGenerator
    from application.ports.repositories.page_repository import PageRepository

logger = structlog.get_logger()


class EmbedCompoundSmilesUseCase:
    """Generate ChemBERTa embeddings for all valid compounds on a page and store in Qdrant.

    Steps:
    1. Load the Page aggregate
    2. Collect all compound_mentions where canonical_smiles is set and is_smiles_valid=True
    3. If none, mark workflow COMPLETED with count=0 and return
    4. Batch-generate ChemBERTa embeddings for all canonical SMILES at once
    5. Upsert all compound embeddings into the compound vector store
    6. Store EmbeddingMetadata on the page (embedding_type="smiles")
    7. Mark SMILES_EMBEDDING_WORKFLOW as COMPLETED
    8. Save the page aggregate
    """

    def __init__(
        self,
        page_repository: PageRepository,
        smiles_embedding_generator: EmbeddingGenerator,
        compound_vector_store: CompoundVectorStore,
    ) -> None:
        self.page_repository = page_repository
        self.smiles_embedding_generator = smiles_embedding_generator
        self.compound_vector_store = compound_vector_store

    async def execute(self, page_id: UUID) -> Result[SmilesEmbeddingDTO, AppError]:
        try:
            logger.info("embed_compound_smiles_start", page_id=str(page_id))

            page = self.page_repository.get_by_id(page_id)

            # Collect compounds with valid canonical SMILES
            valid_compounds = [
                c
                for c in (page.compound_mentions or [])
                if c.is_smiles_valid and c.canonical_smiles
            ]

            skipped = len(page.compound_mentions or []) - len(valid_compounds)

            logger.info(
                "embed_compound_smiles_filtered",
                page_id=str(page_id),
                valid=len(valid_compounds),
                skipped=skipped,
            )

            if not valid_compounds:
                # Nothing to embed — return early
                return Success(
                    SmilesEmbeddingDTO(
                        page_id=page_id,
                        artifact_id=page.artifact_id,
                        embedded_count=0,
                        skipped_count=skipped,
                        model_name="",
                    ),
                )

            # Batch embed all canonical SMILES
            smiles_strings = [c.canonical_smiles for c in valid_compounds]
            embeddings = await self.smiles_embedding_generator.generate_batch_embeddings(
                texts=smiles_strings,
            )

            # Build compound metadata dicts for the vector store
            compound_dicts = [
                {
                    "smiles": c.smiles,
                    "canonical_smiles": c.canonical_smiles,
                    "extracted_id": c.extracted_id,
                    "confidence": c.confidence,
                    "is_smiles_valid": c.is_smiles_valid,
                }
                for c in valid_compounds
            ]

            # Upsert into compound collection (deletes old points first)
            await self.compound_vector_store.upsert_compound_embeddings(
                page_id=page_id,
                artifact_id=page.artifact_id,
                page_index=page.index,
                compounds=compound_dicts,
                embeddings=embeddings,
            )

            logger.info(
                "embed_compound_smiles_stored",
                page_id=str(page_id),
                count=len(embeddings),
            )

            # Store lightweight metadata on the aggregate
            first = embeddings[0]
            smiles_embedding_metadata = EmbeddingMetadata(
                embedding_id=first.embedding_id,
                model_name=first.model_name,
                dimensions=first.dimensions,
                generated_at=first.generated_at,
                embedding_type="smiles",
            )
            page.update_smiles_embedding_metadata(smiles_embedding_metadata)

            self.page_repository.save(page)

            logger.info(
                "embed_compound_smiles_success",
                page_id=str(page_id),
                embedded=len(valid_compounds),
            )

            return Success(
                SmilesEmbeddingDTO(
                    page_id=page_id,
                    artifact_id=page.artifact_id,
                    embedded_count=len(valid_compounds),
                    skipped_count=skipped,
                    model_name=first.model_name,
                ),
            )

        except AggregateNotFoundError as e:
            logger.warning("embed_compound_smiles_not_found", page_id=str(page_id), error=str(e))
            return Failure(AppError("not_found", str(e)))
        except Exception as e:
            logger.exception(
                "embed_compound_smiles_unexpected_error",
                page_id=str(page_id),
                error=str(e),
            )
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))
