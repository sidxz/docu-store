"""Tests for embedding use cases."""

from __future__ import annotations

from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.embedding_dtos import SearchRequest
from application.use_cases.embedding_use_cases import (
    GeneratePageEmbeddingUseCase,
    SearchSimilarPagesUseCase,
)
from application.ports.vector_store import PageSearchResult
from domain.aggregates.page import Page
from domain.value_objects.text_mention import TextMention
from domain.value_objects.embedding_metadata import EmbeddingMetadata
from tests.mocks import (
    MockArtifactReadModel,
    MockEmbeddingGenerator,
    MockPageReadModel,
    MockPageRepository,
    MockTextChunker,
    MockVectorStore,
    make_embedding,
)


def _page_with_text(text: str) -> Page:
    page = Page.create(name="Test Page", artifact_id=uuid4(), index=0)
    page.update_text_mention(TextMention(text=text))
    return page


def _page_with_embedding(text: str) -> Page:
    page = _page_with_text(text)
    emb = make_embedding()
    from datetime import UTC, datetime
    meta = EmbeddingMetadata(
        embedding_id=emb.embedding_id,
        model_name=emb.model_name,
        dimensions=emb.dimensions,
        generated_at=datetime.now(UTC),
        embedding_type="text",
    )
    page.update_text_embedding_metadata(meta)
    return page


class TestGeneratePageEmbeddingUseCase:

    @pytest.mark.asyncio
    async def test_success_generates_and_stores_chunks(self) -> None:
        page = _page_with_text("A" * 200)
        repo = MockPageRepository()
        repo.pages[page.id] = page

        generator = MockEmbeddingGenerator()
        vector_store = MockVectorStore()
        chunker = MockTextChunker(num_chunks=2)

        use_case = GeneratePageEmbeddingUseCase(repo, generator, vector_store, chunker)
        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        dto = result.unwrap()
        assert dto.page_id == page.id
        assert dto.artifact_id == page.artifact_id

        assert len(chunker.chunk_calls) == 1
        assert len(generator.generate_batch_calls) == 1
        assert len(generator.generate_batch_calls[0]) == 2  # 2 chunks
        assert len(vector_store.upsert_chunk_calls) == 1
        assert repo.save_called

    @pytest.mark.asyncio
    async def test_skips_if_embedding_already_exists(self) -> None:
        page = _page_with_embedding("Some text here")
        repo = MockPageRepository()
        repo.pages[page.id] = page

        generator = MockEmbeddingGenerator()
        vector_store = MockVectorStore()
        chunker = MockTextChunker()

        use_case = GeneratePageEmbeddingUseCase(repo, generator, vector_store, chunker)
        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        # Should skip: no chunking, no batch generation, no upsert
        assert len(chunker.chunk_calls) == 0
        assert len(generator.generate_batch_calls) == 0
        assert len(vector_store.upsert_chunk_calls) == 0

    @pytest.mark.asyncio
    async def test_force_regenerate_overwrites_existing(self) -> None:
        page = _page_with_embedding("Some text here")
        repo = MockPageRepository()
        repo.pages[page.id] = page

        generator = MockEmbeddingGenerator()
        vector_store = MockVectorStore()
        chunker = MockTextChunker(num_chunks=1)

        use_case = GeneratePageEmbeddingUseCase(repo, generator, vector_store, chunker)
        result = await use_case.execute(page.id, force_regenerate=True)

        assert isinstance(result, Success)
        assert len(generator.generate_batch_calls) == 1
        assert len(vector_store.upsert_chunk_calls) == 1

    @pytest.mark.asyncio
    async def test_fails_when_page_has_no_text(self) -> None:
        page = Page.create(name="Empty Page", artifact_id=uuid4(), index=0)
        repo = MockPageRepository()
        repo.pages[page.id] = page

        use_case = GeneratePageEmbeddingUseCase(
            repo, MockEmbeddingGenerator(), MockVectorStore(), MockTextChunker()
        )
        result = await use_case.execute(page.id)

        assert isinstance(result, Failure)
        assert result.failure().category == "validation"

    @pytest.mark.asyncio
    async def test_fails_when_page_not_found(self) -> None:
        use_case = GeneratePageEmbeddingUseCase(
            MockPageRepository(), MockEmbeddingGenerator(), MockVectorStore(), MockTextChunker()
        )
        result = await use_case.execute(uuid4())

        assert isinstance(result, Failure)
        assert result.failure().category == "not_found"

    @pytest.mark.asyncio
    async def test_fails_when_embedding_generator_raises(self) -> None:
        page = _page_with_text("Hello world text content for embedding")
        repo = MockPageRepository()
        repo.pages[page.id] = page

        generator = MockEmbeddingGenerator(raise_on_call=RuntimeError("GPU OOM"))
        use_case = GeneratePageEmbeddingUseCase(
            repo, generator, MockVectorStore(), MockTextChunker(num_chunks=1)
        )
        result = await use_case.execute(page.id)

        assert isinstance(result, Failure)
        assert result.failure().category == "internal_error"

    @pytest.mark.asyncio
    async def test_returned_dto_reflects_embedding_metadata(self) -> None:
        page = _page_with_text("B" * 300)
        repo = MockPageRepository()
        repo.pages[page.id] = page

        generator = MockEmbeddingGenerator(model_name="my-model", dims=8)
        use_case = GeneratePageEmbeddingUseCase(
            repo, generator, MockVectorStore(), MockTextChunker(num_chunks=1)
        )
        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        dto = result.unwrap()
        assert dto.model_name == "my-model"
        assert dto.dimensions == 8


class TestSearchSimilarPagesUseCase:

    def _make_search_result(self, page_id, artifact_id, score=0.9) -> PageSearchResult:
        return PageSearchResult(
            page_id=page_id,
            artifact_id=artifact_id,
            score=score,
            page_index=0,
        )

    @pytest.mark.asyncio
    async def test_success_returns_deduplicated_results(self) -> None:
        page_id = uuid4()
        artifact_id = uuid4()

        # Two results for same page (different chunks) — should be deduplicated
        results = [
            self._make_search_result(page_id, artifact_id, score=0.95),
            self._make_search_result(page_id, artifact_id, score=0.80),
        ]
        vector_store = MockVectorStore(search_results=results)
        generator = MockEmbeddingGenerator()

        use_case = SearchSimilarPagesUseCase(
            generator, vector_store, MockPageReadModel(), MockArtifactReadModel()
        )
        request = SearchRequest(query_text="test query", limit=10)
        result = await use_case.execute(request)

        assert isinstance(result, Success)
        response = result.unwrap()
        # Deduplicated: only 1 unique page
        assert response.total_results == 1
        assert response.results[0].similarity_score == 0.95  # highest score wins

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_response(self) -> None:
        use_case = SearchSimilarPagesUseCase(
            MockEmbeddingGenerator(), MockVectorStore(), MockPageReadModel(), MockArtifactReadModel()
        )
        result = await use_case.execute(SearchRequest(query_text="nothing here"))

        assert isinstance(result, Success)
        assert result.unwrap().total_results == 0
        assert result.unwrap().results == []

    @pytest.mark.asyncio
    async def test_enriches_results_with_read_model_data(self) -> None:
        page_id = uuid4()
        artifact_id = uuid4()

        # Build a fake PageResponse-like object with text_mention
        from types import SimpleNamespace
        fake_page = SimpleNamespace(
            page_id=page_id,
            text_mention=SimpleNamespace(text="Page text preview"),
        )
        fake_artifact = SimpleNamespace(
            artifact_id=artifact_id,
            source_filename="paper.pdf",
            source_uri=None,
            artifact_type="research_article",
            mime_type="application/pdf",
            storage_location="/s/paper.pdf",
            pages=[page_id],
            tags=["chemistry"],
            summary_candidate=None,
            title_mention=None,
        )

        vector_store = MockVectorStore(
            search_results=[self._make_search_result(page_id, artifact_id)]
        )
        use_case = SearchSimilarPagesUseCase(
            MockEmbeddingGenerator(),
            vector_store,
            MockPageReadModel({page_id: fake_page}),
            MockArtifactReadModel({artifact_id: fake_artifact}),
        )
        result = await use_case.execute(SearchRequest(query_text="chemistry query"))

        assert isinstance(result, Success)
        dto = result.unwrap().results[0]
        assert dto.text_preview == "Page text preview"
        assert dto.artifact_name == "paper.pdf"
        assert dto.artifact_details is not None
        assert dto.artifact_details.page_count == 1

    @pytest.mark.asyncio
    async def test_model_used_comes_from_generator(self) -> None:
        use_case = SearchSimilarPagesUseCase(
            MockEmbeddingGenerator(model_name="special-model"),
            MockVectorStore(),
            MockPageReadModel(),
            MockArtifactReadModel(),
        )
        result = await use_case.execute(SearchRequest(query_text="query"))

        assert isinstance(result, Success)
        assert result.unwrap().model_used == "special-model"

    @pytest.mark.asyncio
    async def test_respects_limit(self) -> None:
        page_ids = [uuid4() for _ in range(5)]
        artifact_id = uuid4()
        results = [self._make_search_result(pid, artifact_id, score=0.9 - i * 0.1)
                   for i, pid in enumerate(page_ids)]

        vector_store = MockVectorStore(search_results=results)
        use_case = SearchSimilarPagesUseCase(
            MockEmbeddingGenerator(), vector_store, MockPageReadModel(), MockArtifactReadModel()
        )
        result = await use_case.execute(SearchRequest(query_text="query", limit=3))

        assert isinstance(result, Success)
        assert result.unwrap().total_results == 3

    @pytest.mark.asyncio
    async def test_fails_when_generator_raises(self) -> None:
        use_case = SearchSimilarPagesUseCase(
            MockEmbeddingGenerator(raise_on_call=RuntimeError("network error")),
            MockVectorStore(),
            MockPageReadModel(),
            MockArtifactReadModel(),
        )
        result = await use_case.execute(SearchRequest(query_text="query"))

        assert isinstance(result, Failure)
        assert result.failure().category == "internal_error"
