"""Tests for SMILES embedding use cases."""

from __future__ import annotations

from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.use_cases.smiles_embedding_use_cases import EmbedCompoundSmilesUseCase
from domain.aggregates.page import Page
from domain.value_objects.compound_mention import CompoundMention
from tests.mocks import (
    MockCompoundVectorStore,
    MockEmbeddingGenerator,
    MockPageRepository,
)


def _make_valid_compound(smiles: str = "c1ccccc1", canonical: str = "c1ccccc1") -> CompoundMention:
    return CompoundMention(
        smiles=smiles,
        canonical_smiles=canonical,
        is_smiles_valid=True,
        extracted_id="Test",
        confidence=0.9,
    )


def _make_invalid_compound() -> CompoundMention:
    return CompoundMention(
        smiles="bad-smiles",
        canonical_smiles=None,
        is_smiles_valid=False,
        extracted_id="Bad",
        confidence=0.3,
    )


def _page_with_compounds(compounds: list[CompoundMention]) -> Page:
    page = Page.create(name="Page", artifact_id=uuid4(), index=0)
    page.update_compound_mentions(compounds)
    return page


class TestEmbedCompoundSmilesUseCase:

    @pytest.mark.asyncio
    async def test_success_embeds_valid_compounds(self) -> None:
        compounds = [_make_valid_compound("c1ccccc1", "c1ccccc1"),
                     _make_valid_compound("CCO", "CCO")]
        page = _page_with_compounds(compounds)

        repo = MockPageRepository()
        repo.pages[page.id] = page
        generator = MockEmbeddingGenerator()
        vector_store = MockCompoundVectorStore()

        use_case = EmbedCompoundSmilesUseCase(repo, generator, vector_store)
        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        dto = result.unwrap()
        assert dto.embedded_count == 2
        assert dto.skipped_count == 0
        assert dto.page_id == page.id

    @pytest.mark.asyncio
    async def test_skips_invalid_compounds(self) -> None:
        compounds = [_make_valid_compound(), _make_invalid_compound(), _make_invalid_compound()]
        page = _page_with_compounds(compounds)

        repo = MockPageRepository()
        repo.pages[page.id] = page
        generator = MockEmbeddingGenerator()
        vector_store = MockCompoundVectorStore()

        use_case = EmbedCompoundSmilesUseCase(repo, generator, vector_store)
        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        dto = result.unwrap()
        assert dto.embedded_count == 1
        assert dto.skipped_count == 2

    @pytest.mark.asyncio
    async def test_early_return_when_no_valid_compounds(self) -> None:
        page = _page_with_compounds([_make_invalid_compound()])

        repo = MockPageRepository()
        repo.pages[page.id] = page
        generator = MockEmbeddingGenerator()
        vector_store = MockCompoundVectorStore()

        use_case = EmbedCompoundSmilesUseCase(repo, generator, vector_store)
        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        dto = result.unwrap()
        assert dto.embedded_count == 0
        assert dto.skipped_count == 1
        # No embeddings generated, no upsert
        assert len(generator.generate_batch_calls) == 0
        assert len(vector_store.upsert_calls) == 0
        # No save because no domain state changed
        assert not repo.save_called

    @pytest.mark.asyncio
    async def test_early_return_when_no_compounds_at_all(self) -> None:
        page = Page.create(name="Empty", artifact_id=uuid4(), index=0)
        repo = MockPageRepository()
        repo.pages[page.id] = page

        use_case = EmbedCompoundSmilesUseCase(repo, MockEmbeddingGenerator(), MockCompoundVectorStore())
        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        assert result.unwrap().embedded_count == 0

    @pytest.mark.asyncio
    async def test_calls_vector_store_upsert(self) -> None:
        compounds = [_make_valid_compound()]
        page = _page_with_compounds(compounds)

        repo = MockPageRepository()
        repo.pages[page.id] = page
        vector_store = MockCompoundVectorStore()

        use_case = EmbedCompoundSmilesUseCase(repo, MockEmbeddingGenerator(), vector_store)
        await use_case.execute(page.id)

        assert len(vector_store.upsert_calls) == 1
        assert vector_store.upsert_calls[0]["page_id"] == page.id
        assert vector_store.upsert_calls[0]["count"] == 1

    @pytest.mark.asyncio
    async def test_saves_embedding_metadata_on_page(self) -> None:
        page = _page_with_compounds([_make_valid_compound()])
        repo = MockPageRepository()
        repo.pages[page.id] = page

        use_case = EmbedCompoundSmilesUseCase(
            repo, MockEmbeddingGenerator(model_name="chemberta"), MockCompoundVectorStore()
        )
        await use_case.execute(page.id)

        assert repo.save_called
        saved_page = repo.pages[page.id]
        assert saved_page.smiles_embedding_metadata is not None
        assert saved_page.smiles_embedding_metadata.embedding_type == "smiles"
        assert saved_page.smiles_embedding_metadata.model_name == "chemberta"

    @pytest.mark.asyncio
    async def test_model_name_in_dto(self) -> None:
        page = _page_with_compounds([_make_valid_compound()])
        repo = MockPageRepository()
        repo.pages[page.id] = page

        use_case = EmbedCompoundSmilesUseCase(
            repo, MockEmbeddingGenerator(model_name="chemberta-v2"), MockCompoundVectorStore()
        )
        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        assert result.unwrap().model_name == "chemberta-v2"

    @pytest.mark.asyncio
    async def test_fails_when_page_not_found(self) -> None:
        use_case = EmbedCompoundSmilesUseCase(
            MockPageRepository(), MockEmbeddingGenerator(), MockCompoundVectorStore()
        )
        result = await use_case.execute(uuid4())

        assert isinstance(result, Failure)
        assert result.failure().category == "not_found"

    @pytest.mark.asyncio
    async def test_fails_when_generator_raises(self) -> None:
        page = _page_with_compounds([_make_valid_compound()])
        repo = MockPageRepository()
        repo.pages[page.id] = page

        generator = MockEmbeddingGenerator(raise_on_call=RuntimeError("GPU unavailable"))
        use_case = EmbedCompoundSmilesUseCase(repo, generator, MockCompoundVectorStore())
        result = await use_case.execute(page.id)

        assert isinstance(result, Failure)
        assert result.failure().category == "internal_error"

    @pytest.mark.asyncio
    async def test_batch_uses_canonical_smiles(self) -> None:
        compounds = [_make_valid_compound("c1ccccc1", "c1ccccc1")]
        page = _page_with_compounds(compounds)
        repo = MockPageRepository()
        repo.pages[page.id] = page

        generator = MockEmbeddingGenerator()
        use_case = EmbedCompoundSmilesUseCase(repo, generator, MockCompoundVectorStore())
        await use_case.execute(page.id)

        # Should have passed canonical_smiles to the batch generator
        assert generator.generate_batch_calls[0] == ["c1ccccc1"]
