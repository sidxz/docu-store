"""Mock implementations for testing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from application.dtos.cser_dtos import CserCompoundResult
from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.repositories.page_repository import PageRepository
from application.ports.vector_store import PageSearchResult
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.exceptions import AggregateNotFoundError
from domain.value_objects.text_chunk import TextChunk
from domain.value_objects.text_embedding import TextEmbedding


# ---------------------------------------------------------------------------
# Repository mocks
# ---------------------------------------------------------------------------


class MockArtifactRepository(ArtifactRepository):
    """Mock implementation of ArtifactRepository for testing."""

    def __init__(self) -> None:
        self.artifacts: dict[UUID, Artifact] = {}
        self.save_called = False
        self.get_by_id_called = False

    def save(self, artifact: Artifact) -> None:
        self.artifacts[artifact.id] = artifact
        self.save_called = True

    def get_by_id(self, artifact_id: UUID) -> Artifact:
        self.get_by_id_called = True
        if artifact_id not in self.artifacts:
            msg = f"Artifact with id {artifact_id} not found"
            raise AggregateNotFoundError(msg)
        return self.artifacts[artifact_id]


class MockPageRepository(PageRepository):
    """Mock implementation of PageRepository for testing."""

    def __init__(self) -> None:
        self.pages: dict[UUID, Page] = {}
        self.save_called = False
        self.get_by_id_called = False

    def save(self, page: Page) -> None:
        self.pages[page.id] = page
        self.save_called = True

    def get_by_id(self, page_id: UUID) -> Page:
        self.get_by_id_called = True
        if page_id not in self.pages:
            msg = f"Page with id {page_id} not found"
            raise AggregateNotFoundError(msg)
        return self.pages[page_id]


# ---------------------------------------------------------------------------
# Event publisher mock
# ---------------------------------------------------------------------------


class MockExternalEventPublisher:
    """Mock implementation of ExternalEventPublisher for testing."""

    def __init__(self) -> None:
        self.artifact_created_called = False
        self.artifact_deleted_called = False
        self.artifact_updated_called = False
        self.page_created_called = False
        self.page_updated_called = False
        self.page_deleted_called = False
        self.artifact_created_data: Any = None
        self.artifact_deleted_data: Any = None
        self.page_updated_data: Any = None

    async def notify_artifact_created(self, artifact: Any) -> None:
        self.artifact_created_called = True
        self.artifact_created_data = artifact

    async def notify_artifact_updated(self, artifact: Any) -> None:
        self.artifact_updated_called = True

    async def notify_artifact_deleted(self, artifact_id: UUID) -> None:
        self.artifact_deleted_called = True
        self.artifact_deleted_data = artifact_id

    async def notify_page_created(self, page: Any) -> None:
        self.page_created_called = True

    async def notify_page_updated(self, page: Any) -> None:
        self.page_updated_called = True
        self.page_updated_data = page

    async def notify_page_deleted(self, page_id: UUID) -> None:
        self.page_deleted_called = True


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------


def make_embedding(model_name: str = "test-model", dims: int = 4) -> TextEmbedding:
    return TextEmbedding(
        embedding_id=uuid4(),
        vector=[0.1] * dims,
        model_name=model_name,
        dimensions=dims,
        generated_at=datetime.now(UTC),
    )


class MockEmbeddingGenerator:
    """Mock implementation of EmbeddingGenerator."""

    def __init__(
        self,
        model_name: str = "test-model",
        dims: int = 4,
        raise_on_call: Exception | None = None,
    ) -> None:
        self.model_name = model_name
        self.dims = dims
        self.raise_on_call = raise_on_call
        self.generate_batch_calls: list[list[str]] = []
        self.generate_text_calls: list[str] = []

    async def generate_text_embedding(
        self,
        text: str,
        model_name: str | None = None,
    ) -> TextEmbedding:
        if self.raise_on_call:
            raise self.raise_on_call
        self.generate_text_calls.append(text)
        return make_embedding(self.model_name, self.dims)

    async def generate_batch_embeddings(
        self,
        texts: list[str],
        model_name: str | None = None,
    ) -> list[TextEmbedding]:
        if self.raise_on_call:
            raise self.raise_on_call
        self.generate_batch_calls.append(texts)
        return [make_embedding(self.model_name, self.dims) for _ in texts]

    async def get_model_info(self) -> dict[str, str | int]:
        return {"model_name": self.model_name, "dimensions": self.dims, "provider": "mock"}


# ---------------------------------------------------------------------------
# Vector store mocks
# ---------------------------------------------------------------------------


class MockVectorStore:
    """Mock implementation of VectorStore."""

    def __init__(self, search_results: list[PageSearchResult] | None = None) -> None:
        self.upsert_chunk_calls: list[dict] = []
        self.search_calls: list[dict] = []
        self._search_results = search_results or []

    async def ensure_collection_exists(self) -> None:
        pass

    async def upsert_page_chunk_embeddings(
        self,
        page_id: UUID,
        artifact_id: UUID,
        embeddings: list[TextEmbedding],
        page_index: int,
        chunk_count: int,
        metadata: dict | None = None,
    ) -> None:
        self.upsert_chunk_calls.append(
            {"page_id": page_id, "embeddings": embeddings, "chunk_count": chunk_count}
        )

    async def search_similar_pages(
        self,
        query_embedding: TextEmbedding,
        limit: int = 10,
        artifact_id_filter: UUID | None = None,
        score_threshold: float | None = None,
    ) -> list[PageSearchResult]:
        self.search_calls.append({"limit": limit, "filter": artifact_id_filter})
        return self._search_results

    async def get_collection_info(self) -> dict:
        return {}


class MockCompoundVectorStore:
    """Mock implementation of CompoundVectorStore."""

    def __init__(self) -> None:
        self.upsert_calls: list[dict] = []

    async def ensure_compound_collection_exists(self) -> None:
        pass

    async def upsert_compound_embeddings(
        self,
        page_id: UUID,
        artifact_id: UUID,
        page_index: int,
        compounds: list[dict],
        embeddings: list[TextEmbedding],
    ) -> None:
        self.upsert_calls.append({"page_id": page_id, "count": len(embeddings)})

    async def delete_compound_embeddings_for_page(self, page_id: UUID) -> None:
        pass

    async def search_similar_compounds(self, *args: Any, **kwargs: Any) -> list:
        return []

    async def get_compound_collection_info(self) -> dict:
        return {}


# ---------------------------------------------------------------------------
# Text chunker mock
# ---------------------------------------------------------------------------


class MockTextChunker:
    """Mock implementation of TextChunker."""

    def __init__(self, num_chunks: int = 2) -> None:
        self.num_chunks = num_chunks
        self.chunk_calls: list[str] = []

    def chunk_text(self, text: str) -> list[TextChunk]:
        self.chunk_calls.append(text)
        chunk_size = max(1, len(text) // self.num_chunks)
        chunks = []
        for i in range(self.num_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, len(text))
            chunk_text_val = text[start:end] or text[:1]
            chunks.append(
                TextChunk(
                    chunk_index=i,
                    text=chunk_text_val,
                    start_char=start,
                    end_char=end,
                    total_chunks=self.num_chunks,
                )
            )
        return chunks


# ---------------------------------------------------------------------------
# CSER / SMILES mocks
# ---------------------------------------------------------------------------


class MockCserService:
    """Mock implementation of CserService."""

    def __init__(self, results: list[CserCompoundResult] | None = None) -> None:
        self._results = results or []
        self.extract_calls: list[dict] = []

    def extract_compounds_from_pdf_page(
        self, storage_key: str, page_index: int
    ) -> list[CserCompoundResult]:
        self.extract_calls.append({"storage_key": storage_key, "page_index": page_index})
        return self._results


class MockSmilesValidator:
    """Mock implementation of SmilesValidator."""

    def __init__(self, valid: bool = True, canonical: str | None = "C") -> None:
        self._valid = valid
        self._canonical = canonical

    def validate(self, smiles: str) -> bool:
        return self._valid

    def canonicalize(self, smiles: str) -> str | None:
        return self._canonical if self._valid else None


# ---------------------------------------------------------------------------
# Blob store mock
# ---------------------------------------------------------------------------


class MockBlobStore:
    """Mock implementation of BlobStore."""

    def __init__(
        self,
        exists_result: bool = True,
        bytes_result: bytes = b"fake-image-data",
    ) -> None:
        self._exists = exists_result
        self._bytes = bytes_result
        self.exists_calls: list[str] = []
        self.get_bytes_calls: list[str] = []

    def exists(self, key: str) -> bool:
        self.exists_calls.append(key)
        return self._exists

    def get_bytes(self, key: str) -> bytes:
        self.get_bytes_calls.append(key)
        return self._bytes

    def put_stream(self, key: str, stream: Any, *, mime_type: str | None = None) -> Any:
        pass

    def get_stream(self, key: str) -> Any:
        pass

    def delete(self, key: str) -> None:
        pass


# ---------------------------------------------------------------------------
# LLM / prompt mocks
# ---------------------------------------------------------------------------


class MockLLMClient:
    """Mock implementation of LLMClientPort."""

    def __init__(
        self,
        response: str = "Mock summary text.",
        raise_on_call: Exception | None = None,
    ) -> None:
        self._response = response
        self.raise_on_call = raise_on_call
        self.complete_calls: list[str] = []
        self.complete_with_image_calls: list[tuple[str, str]] = []

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        if self.raise_on_call:
            raise self.raise_on_call
        self.complete_calls.append(prompt)
        return self._response

    async def complete_with_image(self, prompt: str, image_b64: str, **kwargs: Any) -> str:
        if self.raise_on_call:
            raise self.raise_on_call
        self.complete_with_image_calls.append((prompt, image_b64))
        return self._response

    async def get_model_info(self) -> dict[str, str]:
        return {"provider": "mock", "model_name": "mock-model"}


class MockPromptRepository:
    """Mock implementation of PromptRepositoryPort."""

    def __init__(self, rendered: str = "Rendered prompt text.") -> None:
        self._rendered = rendered
        self.render_calls: list[dict] = []

    async def render_prompt(self, name: str, version: str | None = None, **variables: str) -> str:
        self.render_calls.append({"name": name, **variables})
        return self._rendered


# ---------------------------------------------------------------------------
# Read model mocks
# ---------------------------------------------------------------------------


class MockPageReadModel:
    """Mock implementation of PageReadModel."""

    def __init__(self, pages: dict[UUID, Any] | None = None) -> None:
        self._pages = pages or {}

    async def get_page_by_id(self, page_id: UUID) -> Any:
        return self._pages.get(page_id)

    async def list_pages(self, *args: Any, **kwargs: Any) -> list:
        return list(self._pages.values())


class MockArtifactReadModel:
    """Mock implementation of ArtifactReadModel."""

    def __init__(self, artifacts: dict[UUID, Any] | None = None) -> None:
        self._artifacts = artifacts or {}

    async def get_artifact_by_id(self, artifact_id: UUID) -> Any:
        return self._artifacts.get(artifact_id)

    async def list_artifacts(self, *args: Any, **kwargs: Any) -> list:
        return list(self._artifacts.values())


# ---------------------------------------------------------------------------
# Workflow orchestrator mock
# ---------------------------------------------------------------------------


class MockWorkflowOrchestrator:
    """Mock implementation of WorkflowOrchestrator."""

    def __init__(self, raise_on_call: Exception | None = None) -> None:
        self.raise_on_call = raise_on_call
        self.artifact_processing_calls: list[dict] = []
        self.embedding_calls: list[UUID] = []
        self.compound_extraction_calls: list[UUID] = []
        self.smiles_embedding_calls: list[UUID] = []
        self.page_summarization_calls: list[UUID] = []

    async def start_artifact_processing_workflow(
        self, artifact_id: UUID, storage_location: str
    ) -> None:
        if self.raise_on_call:
            raise self.raise_on_call
        self.artifact_processing_calls.append(
            {"artifact_id": artifact_id, "storage_location": storage_location}
        )

    async def start_embedding_workflow(self, page_id: UUID) -> None:
        if self.raise_on_call:
            raise self.raise_on_call
        self.embedding_calls.append(page_id)

    async def start_compound_extraction_workflow(self, page_id: UUID) -> None:
        if self.raise_on_call:
            raise self.raise_on_call
        self.compound_extraction_calls.append(page_id)

    async def start_smiles_embedding_workflow(self, page_id: UUID) -> None:
        if self.raise_on_call:
            raise self.raise_on_call
        self.smiles_embedding_calls.append(page_id)

    async def start_page_summarization_workflow(self, page_id: UUID) -> None:
        if self.raise_on_call:
            raise self.raise_on_call
        self.page_summarization_calls.append(page_id)

    async def get_page_workflow_statuses(self, page_id: UUID) -> dict:
        return {}

    async def get_artifact_workflow_statuses(self, artifact_id: UUID) -> dict:
        return {}
