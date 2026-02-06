"""Tests for page use cases."""

from __future__ import annotations

from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.page_dtos import AddCompoundMentionsRequest, CreatePageRequest
from application.use_cases.page_use_cases import (
    AddCompoundMentionsUseCase,
    CreatePageUseCase,
    DeletePageUseCase,
    UpdateSummaryCandidateUseCase,
    UpdateTagMentionsUseCase,
    UpdateTextMentionUseCase,
)
from domain.aggregates.page import Page
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from tests.mocks import MockArtifactRepository, MockPageRepository


class TestCreatePageUseCase:
    """Test CreatePageUseCase."""

    @pytest.mark.asyncio
    async def test_create_page_success(self, sample_artifact) -> None:
        """Test successfully creating a page."""
        page_repo = MockPageRepository()
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(sample_artifact)

        use_case = CreatePageUseCase(page_repo, artifact_repo)
        request = CreatePageRequest(
            name="Introduction",
            artifact_id=sample_artifact.id,
            index=0,
        )

        result = await use_case.execute(request)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.name == "Introduction"
        assert response.artifact_id == sample_artifact.id
        assert page_repo.save_called is True
        assert artifact_repo.save_called is True

    @pytest.mark.asyncio
    async def test_create_page_artifact_not_found(self) -> None:
        """Test creating a page when artifact doesn't exist."""
        page_repo = MockPageRepository()
        artifact_repo = MockArtifactRepository()

        use_case = CreatePageUseCase(page_repo, artifact_repo)
        request = CreatePageRequest(
            name="Introduction",
            artifact_id=uuid4(),
            index=0,
        )

        result = await use_case.execute(request)

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"
        assert page_repo.save_called is False


class TestAddCompoundMentionsUseCase:
    """Test AddCompoundMentionsUseCase."""

    @pytest.mark.asyncio
    async def test_add_compound_mentions_success(self, sample_page) -> None:
        """Test successfully adding compound mentions."""
        page_repo = MockPageRepository()
        page_repo.save(sample_page)

        use_case = AddCompoundMentionsUseCase(page_repo)
        request = AddCompoundMentionsRequest(
            page_id=sample_page.id,
            compound_mentions=[
                CompoundMention(smiles="C1=CC=CC=C1", extracted_name="Benzene"),
            ],
        )

        result = await use_case.execute(request)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert len(response.compound_mentions) == 1

    @pytest.mark.asyncio
    async def test_add_compound_mentions_page_not_found(self) -> None:
        """Test adding compound mentions when page doesn't exist."""
        page_repo = MockPageRepository()
        use_case = AddCompoundMentionsUseCase(page_repo)

        request = AddCompoundMentionsRequest(
            page_id=uuid4(),
            compound_mentions=[
                CompoundMention(smiles="C1=CC=CC=C1", extracted_name="Benzene"),
            ],
        )

        result = await use_case.execute(request)

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"


class TestUpdateTagMentionsUseCase:
    """Test UpdateTagMentionsUseCase."""

    @pytest.mark.asyncio
    async def test_update_tag_mentions_success(self, sample_page) -> None:
        """Test successfully updating tag mentions."""
        page_repo = MockPageRepository()
        page_repo.save(sample_page)

        use_case = UpdateTagMentionsUseCase(page_repo)
        mentions = [TagMention(tag="chemistry", confidence=0.88)]

        result = await use_case.execute(sample_page.id, mentions)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.tag_mentions == mentions

    @pytest.mark.asyncio
    async def test_update_tag_mentions_page_not_found(self) -> None:
        """Test updating tag mentions when page doesn't exist."""
        page_repo = MockPageRepository()
        use_case = UpdateTagMentionsUseCase(page_repo)

        result = await use_case.execute(uuid4(), [TagMention(tag="chemistry", confidence=0.88)])

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"


class TestUpdateTextMentionUseCase:
    """Test UpdateTextMentionUseCase."""

    @pytest.mark.asyncio
    async def test_update_text_mention_success(self, sample_page) -> None:
        """Test successfully updating text mention."""
        page_repo = MockPageRepository()
        page_repo.save(sample_page)

        use_case = UpdateTextMentionUseCase(page_repo)
        mention = TextMention(text="Important", confidence=0.9)

        result = await use_case.execute(sample_page.id, mention)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.text_mention == mention

    @pytest.mark.asyncio
    async def test_update_text_mention_page_not_found(self) -> None:
        """Test updating text mention when page doesn't exist."""
        page_repo = MockPageRepository()
        use_case = UpdateTextMentionUseCase(page_repo)

        result = await use_case.execute(uuid4(), TextMention(text="Important", confidence=0.9))

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"


class TestUpdateSummaryCandidateUseCase:
    """Test UpdateSummaryCandidateUseCase."""

    @pytest.mark.asyncio
    async def test_update_summary_candidate_success(self, sample_page) -> None:
        """Test successfully updating summary candidate."""
        page_repo = MockPageRepository()
        page_repo.save(sample_page)

        use_case = UpdateSummaryCandidateUseCase(page_repo)
        candidate = SummaryCandidate(summary="Summary", confidence=0.8)

        result = await use_case.execute(sample_page.id, candidate)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.summary_candidate == candidate

    @pytest.mark.asyncio
    async def test_update_summary_candidate_page_not_found(self) -> None:
        """Test updating summary candidate when page doesn't exist."""
        page_repo = MockPageRepository()
        use_case = UpdateSummaryCandidateUseCase(page_repo)

        result = await use_case.execute(
            uuid4(),
            SummaryCandidate(summary="Summary", confidence=0.8),
        )

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"


class TestDeletePageUseCase:
    """Test DeletePageUseCase."""

    @pytest.mark.asyncio
    async def test_delete_page_success(self, sample_artifact) -> None:
        """Test successfully deleting a page."""
        page_repo = MockPageRepository()
        artifact_repo = MockArtifactRepository()

        page = Page.create(name="Page 1", artifact_id=sample_artifact.id)
        sample_artifact.add_pages([page.id])
        page_repo.save(page)
        artifact_repo.save(sample_artifact)

        use_case = DeletePageUseCase(page_repo, artifact_repo)

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        assert page_repo.pages[page.id].is_deleted is True
        assert artifact_repo.artifacts[sample_artifact.id].pages == ()

    @pytest.mark.asyncio
    async def test_delete_page_not_found(self) -> None:
        """Test deleting a non-existent page."""
        page_repo = MockPageRepository()
        artifact_repo = MockArtifactRepository()
        use_case = DeletePageUseCase(page_repo, artifact_repo)

        result = await use_case.execute(uuid4())

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"
