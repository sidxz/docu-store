from uuid import UUID

import structlog
from returns.result import Failure, Result, Success

from application.dtos.embedding_dtos import EmbeddingDTO, SearchRequest, SearchResponse
from application.dtos.errors import AppError
from application.dtos.workflow_dtos import WorkflowNames
from application.ports.embedding_generator import EmbeddingGenerator
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.page_read_models import PageReadModel
from application.ports.repositories.page_repository import PageRepository
from application.ports.text_chunker import TextChunker
from application.ports.vector_store import PageSearchResult, VectorStore
from domain.exceptions import AggregateNotFoundError
from domain.value_objects.embedding_metadata import EmbeddingMetadata
from domain.value_objects.workflow_status import WorkflowStatus

logger = structlog.get_logger()


class GeneratePageEmbeddingUseCase:
    """Use case for generating and storing page embeddings with chunking.

    This use case:
    1. Retrieves the page from the repository
    2. Chunks the page text into overlapping segments
    3. Generates embeddings for all chunks in a batch
    4. Stores all chunk embeddings in the vector store
    5. Updates the domain aggregate with embedding metadata
    """

    def __init__(
        self,
        page_repository: PageRepository,
        embedding_generator: EmbeddingGenerator,
        vector_store: VectorStore,
        text_chunker: TextChunker,
    ) -> None:
        self.page_repository = page_repository
        self.embedding_generator = embedding_generator
        self.vector_store = vector_store
        self.text_chunker = text_chunker

    async def execute(
        self,
        page_id: UUID,
        force_regenerate: bool = False,
    ) -> Result[EmbeddingDTO, AppError]:
        """Generate and store embeddings for a page (with chunking).

        Args:
            page_id: The ID of the page to generate embedding for
            force_regenerate: If True, regenerate even if embedding exists

        Returns:
            Result containing EmbeddingDTO on success or AppError on failure

        """
        try:
            logger.info("generate_page_embedding_start", page_id=str(page_id))

            # 1. Retrieve the page aggregate
            page = self.page_repository.get_by_id(page_id)

            # 2. Check if we should skip generation
            if not force_regenerate and page.text_embedding_metadata is not None:
                logger.info(
                    "embedding_already_exists",
                    page_id=str(page_id),
                    embedding_id=str(page.text_embedding_metadata.embedding_id),
                )
                return Success(
                    EmbeddingDTO(
                        embedding_id=page.text_embedding_metadata.embedding_id,
                        page_id=page_id,
                        artifact_id=page.artifact_id,
                        model_name=page.text_embedding_metadata.model_name,
                        dimensions=page.text_embedding_metadata.dimensions,
                        generated_at=page.text_embedding_metadata.generated_at.isoformat(),
                    ),
                )

            # 3. Ensure the page has text content
            if not page.text_mention or not page.text_mention.text:
                msg = f"Page {page_id} has no text content to embed"
                logger.warning("no_text_content", page_id=str(page_id))
                return Failure(AppError("validation", msg))

            # 4. Chunk the page text
            chunks = self.text_chunker.chunk_text(page.text_mention.text)
            logger.info(
                "text_chunked",
                page_id=str(page_id),
                num_chunks=len(chunks),
                text_length=len(page.text_mention.text),
            )

            # 5. Generate embeddings for all chunks in a batch
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = await self.embedding_generator.generate_batch_embeddings(
                texts=chunk_texts,
            )

            # 6. Store all chunk embeddings in vector store
            logger.info(
                "storing_chunk_embeddings",
                page_id=str(page_id),
                chunk_count=len(embeddings),
            )
            await self.vector_store.upsert_page_chunk_embeddings(
                page_id=page_id,
                artifact_id=page.artifact_id,
                embeddings=embeddings,
                page_index=page.index,
                chunk_count=len(chunks),
            )

            # 7. Update domain aggregate with metadata (using first embedding as reference)
            first_embedding = embeddings[0]
            embedding_metadata = EmbeddingMetadata(
                embedding_id=first_embedding.embedding_id,
                model_name=first_embedding.model_name,
                dimensions=first_embedding.dimensions,
                generated_at=first_embedding.generated_at,
                embedding_type="text",
            )
            page.update_text_embedding_metadata(embedding_metadata)

            existing = page.workflow_statuses.get(WorkflowNames.EMBEDDING_WORKFLOW)
            page.update_workflow_status(
                WorkflowNames.EMBEDDING_WORKFLOW,
                WorkflowStatus.completed(
                    message=f"generated embeddings for {len(chunks)} chunks",
                    workflow_id=existing.workflow_id if existing else None,
                    started_at=existing.started_at if existing else None,
                ),
            )

            # 8. Save the updated aggregate (with new event)
            self.page_repository.save(page)

            logger.info(
                "generate_page_embedding_success",
                page_id=str(page_id),
                embedding_id=str(first_embedding.embedding_id),
                chunk_count=len(chunks),
            )

            return Success(
                EmbeddingDTO(
                    embedding_id=first_embedding.embedding_id,
                    page_id=page_id,
                    artifact_id=page.artifact_id,
                    model_name=first_embedding.model_name,
                    dimensions=first_embedding.dimensions,
                    generated_at=first_embedding.generated_at.isoformat(),
                ),
            )

        except AggregateNotFoundError as e:
            logger.error("page_not_found", page_id=str(page_id), error=str(e))
            return Failure(AppError("not_found", f"Page not found: {e!s}"))
        except Exception as e:
            logger.error(
                "generate_page_embedding_failed",
                page_id=str(page_id),
                error=str(e),
                exc_info=True,
            )
            return Failure(
                AppError("internal_error", f"Failed to generate embedding: {e!s}"),
            )


class SearchSimilarPagesUseCase:
    """Use case for searching similar pages using vector similarity.

    This use case:
    1. Generates an embedding for the query text
    2. Searches the vector store for similar pages
    3. Enriches results with data from read models (text preview, artifact details)
    """

    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        vector_store: VectorStore,
        page_read_model: PageReadModel,
        artifact_read_model: ArtifactReadModel,
    ) -> None:
        self.embedding_generator = embedding_generator
        self.vector_store = vector_store
        self.page_read_model = page_read_model
        self.artifact_read_model = artifact_read_model

    async def execute(self, request: SearchRequest) -> Result[SearchResponse, AppError]:
        """Search for pages similar to the query text.

        Args:
            request: SearchRequest with query text and filters

        Returns:
            Result containing SearchResponse on success or AppError on failure

        """
        try:
            logger.info(
                "search_similar_pages_start",
                query_length=len(request.query_text),
                limit=request.limit,
            )

            # 1. Generate embedding for query text
            query_embedding = await self.embedding_generator.generate_text_embedding(
                text=request.query_text,
            )

            # 2. Search vector store (request extra results to account for chunk dedup)
            search_results = await self.vector_store.search_similar_pages(
                query_embedding=query_embedding,
                limit=request.limit * 3,  # Over-fetch to handle chunk dedup
                artifact_id_filter=request.artifact_id,
                score_threshold=request.score_threshold,
            )

            # 3. Deduplicate by page_id (keep highest-scoring chunk per page)
            best_by_page: dict[UUID, PageSearchResult] = {}
            for result in search_results:
                existing = best_by_page.get(result.page_id)
                if existing is None or result.score > existing.score:
                    best_by_page[result.page_id] = result

            deduplicated_results = sorted(
                best_by_page.values(),
                key=lambda r: r.score,
                reverse=True,
            )[: request.limit]

            # 4. Enrich results with read model data
            from application.dtos.embedding_dtos import ArtifactDetailsDTO, SearchResultDTO

            result_dtos = []
            for result in deduplicated_results:
                # Fetch page details for text preview
                page = await self.page_read_model.get_page_by_id(result.page_id)
                text_preview = None
                if page and page.text_mention and page.text_mention.text:
                    text_preview = page.text_mention.text

                # Fetch artifact details
                artifact = await self.artifact_read_model.get_artifact_by_id(
                    result.artifact_id,
                )
                artifact_name = artifact.source_filename if artifact else None

                # Build full artifact details if available
                artifact_details = None
                if artifact:
                    # Determine page count
                    page_count = 0
                    if artifact.pages:
                        page_count = (
                            len(artifact.pages)
                            if isinstance(artifact.pages, list)
                            else len(list(artifact.pages))
                        )

                    artifact_details = ArtifactDetailsDTO(
                        artifact_id=artifact.artifact_id,
                        source_uri=artifact.source_uri,
                        source_filename=artifact.source_filename,
                        artifact_type=str(artifact.artifact_type),
                        mime_type=str(artifact.mime_type),
                        storage_location=artifact.storage_location,
                        page_count=page_count,
                        tags=artifact.tags or [],
                        summary=artifact.summary_candidate.text
                        if artifact.summary_candidate
                        else None,
                        title=artifact.title_mention.text if artifact.title_mention else None,
                    )

                result_dto = SearchResultDTO(
                    page_id=result.page_id,
                    artifact_id=result.artifact_id,
                    page_index=result.page_index,
                    similarity_score=result.score,
                    text_preview=text_preview,
                    artifact_name=artifact_name,
                    artifact_details=artifact_details,
                )
                result_dtos.append(result_dto)

            model_info = await self.embedding_generator.get_model_info()

            logger.info(
                "search_similar_pages_success",
                query_length=len(request.query_text),
                results_count=len(result_dtos),
            )

            return Success(
                SearchResponse(
                    query=request.query_text,
                    results=result_dtos,
                    total_results=len(result_dtos),
                    model_used=str(model_info.get("model_name", "unknown")),
                ),
            )

        except Exception as e:
            logger.error(
                "search_similar_pages_failed",
                query=request.query_text[:100],
                error=str(e),
                exc_info=True,
            )
            return Failure(AppError("internal_error", f"Failed to search pages: {e!s}"))
