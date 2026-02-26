"""Search routes for vector similarity search."""

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from lagom import Container

from application.dtos.embedding_dtos import SearchRequest, SearchResponse
from application.dtos.smiles_embedding_dtos import CompoundSearchRequest, CompoundSearchResponse
from application.ports.compound_vector_store import CompoundVectorStore
from application.ports.embedding_generator import EmbeddingGenerator
from application.ports.vector_store import VectorStore
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from application.use_cases.embedding_use_cases import SearchSimilarPagesUseCase
from application.use_cases.smiles_search_use_cases import SearchSimilarCompoundsUseCase
from infrastructure.embeddings.chemberta_generator import ChemBertaEmbeddingGenerator
from interfaces.api.middleware import handle_use_case_errors
from interfaces.dependencies import get_container

logger = structlog.get_logger()

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/pages", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def search_pages(
    request: SearchRequest,
    container: Annotated[Container, Depends(get_container)],
) -> SearchResponse:
    """Search for similar pages using vector similarity.

    Args:
        request: Search request with query text and optional filters
        container: DI container

    Returns:
        Search results with similarity scores

    Example:
        ```
        POST /search/pages
        {
            "query_text": "machine learning algorithms",
            "limit": 10,
            "artifact_id": "optional-artifact-uuid",
            "score_threshold": 0.7
        }
        ```

    """
    logger.info("search_request", query_length=len(request.query_text), limit=request.limit)

    use_case = container[SearchSimilarPagesUseCase]
    # The @handle_use_case_errors decorator will handle unwrapping the result
    return await use_case.execute(request)


@router.post("/pages/{page_id}/generate-embedding", status_code=status.HTTP_202_ACCEPTED)
async def generate_embedding_for_page(
    page_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    force_regenerate: bool = False,  # noqa: FBT001, FBT002
) -> dict[str, str]:
    """Manually trigger embedding generation for a specific page.

    Useful for:
    - Testing the embedding pipeline
    - Regenerating embeddings after model changes
    - Recovering from failed embedding generation

    Args:
        page_id: UUID of the page to generate embeddings for
        container: DI container
        force_regenerate: If True, regenerate even if embedding exists

    Returns:
        202 Accepted: Embedding generation workflow started

    """
    logger.info("manual_embedding_trigger", page_id=str(page_id), force=force_regenerate)

    orchestrator = container[WorkflowOrchestrator]

    try:
        await orchestrator.start_embedding_workflow(page_id=page_id)
        return {
            "status": "accepted",
            "message": f"Embedding generation workflow started for page {page_id}",
            "page_id": str(page_id),
        }
    except Exception as e:
        logger.exception("failed_to_trigger_embedding", page_id=str(page_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start embedding workflow: {e!s}",
        ) from e


@router.post("/compounds", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def search_compounds(
    request: CompoundSearchRequest,
    container: Annotated[Container, Depends(get_container)],
) -> CompoundSearchResponse:
    """Search for structurally similar compounds using SMILES vector similarity.

    The query SMILES is validated, canonicalized, and embedded with ChemBERTa.
    Returns compounds from all ingested documents ranked by structural similarity.

    Example:
        ```
        POST /search/compounds
        {
            "query_smiles": "CC(=O)Oc1ccccc1C(=O)O",
            "limit": 10,
            "score_threshold": 0.8
        }
        ```

    """
    logger.info("compound_search_request", query_smiles=request.query_smiles[:80])
    use_case = container[SearchSimilarCompoundsUseCase]
    return await use_case.execute(request)


@router.get("/health", status_code=status.HTTP_200_OK)
async def search_health(
    container: Annotated[Container, Depends(get_container)],
) -> dict[str, str | dict]:
    """Check health of search/embedding services (text and compound)."""
    generator = container[EmbeddingGenerator]
    vector_store = container[VectorStore]
    chemberta = container[ChemBertaEmbeddingGenerator]
    compound_store = container[CompoundVectorStore]

    try:
        model_info = await generator.get_model_info()
        collection_info = await vector_store.get_collection_info()
        smiles_model_info = await chemberta.get_model_info()
        compound_collection_info = await compound_store.get_compound_collection_info()
    except Exception as e:
        logger.exception("search_health_check_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Search services unhealthy: {e!s}",
        ) from e
    else:
        return {
            "status": "healthy",
            "text_embedding_model": model_info,
            "text_vector_store": collection_info,
            "smiles_embedding_model": smiles_model_info,
            "compound_vector_store": compound_collection_info,
        }
