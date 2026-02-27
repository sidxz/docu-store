"""Use cases for embedding page and artifact summaries into the summary_embeddings collection."""

from uuid import UUID

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.ports.embedding_generator import EmbeddingGenerator
from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.repositories.page_repository import PageRepository
from application.ports.summary_vector_store import SummaryVectorStore
from domain.exceptions import AggregateNotFoundError

logger = structlog.get_logger()


class EmbedPageSummaryUseCase:
    """Embed a page summary and upsert it into the summary_embeddings collection.

    Reads from the domain aggregates (EventStoreDB) — not the read model — so
    there is no eventual-consistency race between the read-model projector and
    the Temporal activity.  This matches the pattern used by SummarizePageUseCase
    and GeneratePageEmbeddingUseCase.
    """

    def __init__(
        self,
        page_repository: PageRepository,
        artifact_repository: ArtifactRepository,
        embedding_generator: EmbeddingGenerator,
        summary_vector_store: SummaryVectorStore,
    ) -> None:
        self.page_repository = page_repository
        self.artifact_repository = artifact_repository
        self.embedding_generator = embedding_generator
        self.summary_vector_store = summary_vector_store

    async def execute(self, page_id: UUID) -> Result[dict, AppError]:
        """Embed the page summary and store it in the summary_embeddings collection.

        Returns:
            Success with a status dict, or Failure with AppError.

        """
        try:
            logger.info("embed_page_summary_start", page_id=str(page_id))

            page = self.page_repository.get_by_id(page_id)

            if page.summary_candidate is None or not page.summary_candidate.summary:
                return Failure(
                    AppError("validation", f"Page {page_id} has no summary to embed")
                )

            summary_text = page.summary_candidate.summary

            # Load artifact for context metadata (title)
            artifact_title = None
            try:
                artifact = self.artifact_repository.get_by_id(page.artifact_id)
                if artifact.title_mention:
                    artifact_title = artifact.title_mention.text
            except AggregateNotFoundError:
                pass  # Title is optional — embed without it

            embedding = await self.embedding_generator.generate_text_embedding(text=summary_text)

            await self.summary_vector_store.upsert_page_summary_embedding(
                page_id=page_id,
                artifact_id=page.artifact_id,
                embedding=embedding,
                summary_text=summary_text,
                artifact_title=artifact_title,
                page_index=page.index,
            )

            logger.info(
                "embed_page_summary_success",
                page_id=str(page_id),
                artifact_id=str(page.artifact_id),
                summary_len=len(summary_text),
            )
            return Success({"status": "success", "page_id": str(page_id)})

        except AggregateNotFoundError as e:
            logger.warning("embed_page_summary_not_found", page_id=str(page_id), error=str(e))
            return Failure(AppError("not_found", str(e)))
        except Exception as e:
            logger.exception("embed_page_summary_failed", page_id=str(page_id), error=str(e))
            return Failure(AppError("internal_error", f"Failed to embed page summary: {e!s}"))


class EmbedArtifactSummaryUseCase:
    """Embed an artifact summary and upsert it into the summary_embeddings collection.

    Reads from the domain aggregate (EventStoreDB) — not the read model — matching
    the pattern used by SummarizeArtifactUseCase.
    """

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        embedding_generator: EmbeddingGenerator,
        summary_vector_store: SummaryVectorStore,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.embedding_generator = embedding_generator
        self.summary_vector_store = summary_vector_store

    async def execute(self, artifact_id: UUID) -> Result[dict, AppError]:
        """Embed the artifact summary and store it in the summary_embeddings collection.

        Returns:
            Success with a status dict, or Failure with AppError.

        """
        try:
            logger.info("embed_artifact_summary_start", artifact_id=str(artifact_id))

            artifact = self.artifact_repository.get_by_id(artifact_id)

            if artifact.summary_candidate is None or not artifact.summary_candidate.summary:
                return Failure(
                    AppError("validation", f"Artifact {artifact_id} has no summary to embed")
                )

            summary_text = artifact.summary_candidate.summary
            artifact_title = artifact.title_mention.text if artifact.title_mention else None
            page_count = len(artifact.pages)

            embedding = await self.embedding_generator.generate_text_embedding(text=summary_text)

            await self.summary_vector_store.upsert_artifact_summary_embedding(
                artifact_id=artifact_id,
                embedding=embedding,
                summary_text=summary_text,
                artifact_title=artifact_title,
                page_count=page_count,
            )

            logger.info(
                "embed_artifact_summary_success",
                artifact_id=str(artifact_id),
                summary_len=len(summary_text),
            )
            return Success({"status": "success", "artifact_id": str(artifact_id)})

        except AggregateNotFoundError as e:
            logger.warning(
                "embed_artifact_summary_not_found", artifact_id=str(artifact_id), error=str(e)
            )
            return Failure(AppError("not_found", str(e)))
        except Exception as e:
            logger.exception(
                "embed_artifact_summary_failed", artifact_id=str(artifact_id), error=str(e)
            )
            return Failure(
                AppError("internal_error", f"Failed to embed artifact summary: {e!s}")
            )
