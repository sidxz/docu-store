"""Tests for compound extraction use cases."""

from __future__ import annotations

from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.cser_dtos import CserCompoundResult
from application.use_cases.compound_use_cases import ExtractCompoundMentionsUseCase
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from tests.mocks import (
    MockArtifactRepository,
    MockCserService,
    MockExternalEventPublisher,
    MockPageRepository,
    MockSmilesValidator,
)


def _make_artifact() -> Artifact:
    return Artifact.create(
        source_uri=None,
        source_filename="paper.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="/storage/paper.pdf",
    )


def _make_page(artifact_id) -> Page:
    return Page.create(name="Page 1", artifact_id=artifact_id, index=0)


def _make_use_case(
    cser_results=None,
    valid=True,
    canonical="C",
    publisher=None,
):
    artifact = _make_artifact()
    page = _make_page(artifact.id)

    artifact_repo = MockArtifactRepository()
    artifact_repo.artifacts[artifact.id] = artifact

    page_repo = MockPageRepository()
    page_repo.pages[page.id] = page

    cser = MockCserService(results=cser_results or [])
    validator = MockSmilesValidator(valid=valid, canonical=canonical)

    use_case = ExtractCompoundMentionsUseCase(
        page_repository=page_repo,
        artifact_repository=artifact_repo,
        cser_service=cser,
        smiles_validator=validator,
        external_event_publisher=publisher,
    )
    return use_case, page, artifact, page_repo, cser


class TestExtractCompoundMentionsUseCase:

    @pytest.mark.asyncio
    async def test_success_with_valid_compounds(self) -> None:
        results = [
            CserCompoundResult(smiles="c1ccccc1", label_text="Benzene", match_confidence=0.95),
            CserCompoundResult(smiles="CCO", label_text="Ethanol", match_confidence=0.88),
        ]
        use_case, page, _, page_repo, cser = _make_use_case(cser_results=results)

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert len(response.compound_mentions) == 2
        assert page_repo.save_called
        assert len(cser.extract_calls) == 1

    @pytest.mark.asyncio
    async def test_extracts_correct_storage_key(self) -> None:
        use_case, page, artifact, _, cser = _make_use_case()
        await use_case.execute(page.id)

        assert cser.extract_calls[0]["storage_key"] == artifact.storage_location
        assert cser.extract_calls[0]["page_index"] == page.index

    @pytest.mark.asyncio
    async def test_skips_results_without_smiles(self) -> None:
        results = [
            CserCompoundResult(smiles=None, label_text="Unknown", match_confidence=0.5),
            CserCompoundResult(smiles="   ", label_text="Blank", match_confidence=0.5),
            CserCompoundResult(smiles="CCO", label_text="Ethanol", match_confidence=0.9),
        ]
        use_case, page, _, page_repo, _ = _make_use_case(cser_results=results)

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        # Only "CCO" should make it through
        assert len(result.unwrap().compound_mentions) == 1

    @pytest.mark.asyncio
    async def test_invalid_smiles_stored_with_flag(self) -> None:
        results = [CserCompoundResult(smiles="invalid-smiles", label_text="X", match_confidence=0.5)]
        use_case, page, _, _, _ = _make_use_case(cser_results=results, valid=False)

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        mention = result.unwrap().compound_mentions[0]
        assert mention.is_smiles_valid is False
        assert mention.canonical_smiles is None

    @pytest.mark.asyncio
    async def test_valid_smiles_gets_canonicalized(self) -> None:
        results = [CserCompoundResult(smiles="c1ccccc1", label_text="Benz", match_confidence=0.9)]
        use_case, page, _, _, _ = _make_use_case(
            cser_results=results, valid=True, canonical="c1ccccc1"
        )

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        mention = result.unwrap().compound_mentions[0]
        assert mention.is_smiles_valid is True
        assert mention.canonical_smiles == "c1ccccc1"

    @pytest.mark.asyncio
    async def test_empty_cser_results_saves_empty_list(self) -> None:
        use_case, page, _, page_repo, _ = _make_use_case(cser_results=[])

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        assert result.unwrap().compound_mentions == []
        assert page_repo.save_called

    @pytest.mark.asyncio
    async def test_notifies_publisher_on_success(self) -> None:
        publisher = MockExternalEventPublisher()
        use_case, page, _, _, _ = _make_use_case(publisher=publisher)

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        assert publisher.page_updated_called

    @pytest.mark.asyncio
    async def test_fails_when_page_not_found(self) -> None:
        use_case, _, _, _, _ = _make_use_case()

        result = await use_case.execute(uuid4())  # random ID not in repo

        assert isinstance(result, Failure)
        assert result.failure().category == "not_found"

    @pytest.mark.asyncio
    async def test_fails_when_artifact_not_found(self) -> None:
        page = Page.create(name="P", artifact_id=uuid4(), index=0)
        page_repo = MockPageRepository()
        page_repo.pages[page.id] = page

        # Artifact repo is empty — get_by_id will raise AggregateNotFoundError
        use_case = ExtractCompoundMentionsUseCase(
            page_repository=page_repo,
            artifact_repository=MockArtifactRepository(),
            cser_service=MockCserService(),
            smiles_validator=MockSmilesValidator(),
        )
        result = await use_case.execute(page.id)

        assert isinstance(result, Failure)
        assert result.failure().category == "not_found"

    @pytest.mark.asyncio
    async def test_handles_unexpected_exception(self) -> None:
        artifact = _make_artifact()
        page = _make_page(artifact.id)

        artifact_repo = MockArtifactRepository()
        artifact_repo.artifacts[artifact.id] = artifact
        page_repo = MockPageRepository()
        page_repo.pages[page.id] = page

        class ExplodingCser:
            def extract_compounds_from_pdf_page(self, storage_key, page_index):
                raise RuntimeError("CSER crashed")

        use_case = ExtractCompoundMentionsUseCase(
            page_repository=page_repo,
            artifact_repository=artifact_repo,
            cser_service=ExplodingCser(),
            smiles_validator=MockSmilesValidator(),
        )
        result = await use_case.execute(page.id)

        assert isinstance(result, Failure)
        assert result.failure().category == "internal_error"
