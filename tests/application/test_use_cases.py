"""Tests for artifact use cases."""

from __future__ import annotations

from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.artifact_dtos import CreateArtifactRequest
from application.use_cases.artifact_use_cases import (
    AddPagesUseCase,
    CreateArtifactUseCase,
    DeleteArtifactUseCase,
    RemovePagesUseCase,
    UpdateSummaryCandidateUseCase,
    UpdateTagsUseCase,
    UpdateTitleMentionUseCase,
)
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.title_mention import TitleMention
from tests.mocks import MockArtifactRepository, MockExternalEventPublisher, MockPageRepository


class TestCreateArtifactUseCase:
    """Test CreateArtifactUseCase."""

    @pytest.mark.asyncio
    async def test_create_artifact_success(self) -> None:
        """Test successfully creating an artifact."""
        repository = MockArtifactRepository()
        use_case = CreateArtifactUseCase(repository)

        request = CreateArtifactRequest(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        result = await use_case.execute(request)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.source_uri == "https://example.com/paper.pdf"
        assert response.source_filename == "paper.pdf"
        assert response.artifact_type == ArtifactType.RESEARCH_ARTICLE
        assert repository.save_called is True

    @pytest.mark.asyncio
    async def test_create_artifact_with_external_publisher(self) -> None:
        """Test creating artifact with external event publisher."""
        repository = MockArtifactRepository()
        publisher = MockExternalEventPublisher()
        use_case = CreateArtifactUseCase(repository, publisher)

        request = CreateArtifactRequest(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        result = await use_case.execute(request)

        assert isinstance(result, Success)
        assert publisher.artifact_created_called is True


class TestAddPagesUseCase:
    """Test AddPagesUseCase."""

    @pytest.mark.asyncio
    async def test_add_pages_success(self, sample_artifact) -> None:
        """Test successfully adding pages to an artifact."""
        from domain.aggregates.page import Page

        artifact_repo = MockArtifactRepository()
        page_repo = MockPageRepository()

        # Setup: save artifact and pages
        artifact_repo.save(sample_artifact)

        page1 = Page.create(name="Page 1", artifact_id=sample_artifact.id, index=0)
        page2 = Page.create(name="Page 2", artifact_id=sample_artifact.id, index=1)

        page_repo.save(page1)
        page_repo.save(page2)

        use_case = AddPagesUseCase(artifact_repo, page_repo)

        result = await use_case.execute(sample_artifact.id, [page1.id, page2.id])

        assert isinstance(result, Success)
        response = result.unwrap()
        assert len(response.pages) == 2

    @pytest.mark.asyncio
    async def test_add_pages_artifact_not_found(self) -> None:
        """Test adding pages when artifact doesn't exist."""
        artifact_repo = MockArtifactRepository()
        page_repo = MockPageRepository()
        use_case = AddPagesUseCase(artifact_repo, page_repo)

        result = await use_case.execute(uuid4(), [uuid4()])

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"

    @pytest.mark.asyncio
    async def test_add_pages_page_not_found(self, sample_artifact) -> None:
        """Test adding pages when page doesn't exist."""
        artifact_repo = MockArtifactRepository()
        page_repo = MockPageRepository()
        artifact_repo.save(sample_artifact)

        use_case = AddPagesUseCase(artifact_repo, page_repo)

        result = await use_case.execute(sample_artifact.id, [uuid4()])

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"

    @pytest.mark.asyncio
    async def test_add_pages_wrong_artifact(self, sample_artifact) -> None:
        """Test adding a page that belongs to a different artifact."""
        artifact_repo = MockArtifactRepository()
        page_repo = MockPageRepository()

        artifact1 = sample_artifact
        artifact_repo.save(artifact1)

        from domain.aggregates.page import Page

        # Create page for a different artifact
        different_artifact_id = uuid4()
        page = Page.create(name="Page", artifact_id=different_artifact_id)
        page_repo.save(page)

        use_case = AddPagesUseCase(artifact_repo, page_repo)

        result = await use_case.execute(artifact1.id, [page.id])

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "validation"


class TestRemovePagesUseCase:
    """Test RemovePagesUseCase."""

    @pytest.mark.asyncio
    async def test_remove_pages_success(self, sample_artifact) -> None:
        """Test successfully removing pages from an artifact."""
        artifact_repo = MockArtifactRepository()

        from uuid import uuid4

        page_id = uuid4()
        sample_artifact.add_pages([page_id])
        artifact_repo.save(sample_artifact)

        use_case = RemovePagesUseCase(artifact_repo)

        result = await use_case.execute(sample_artifact.id, [page_id])

        assert isinstance(result, Success)
        response = result.unwrap()
        assert len(response.pages) == 0

    @pytest.mark.asyncio
    async def test_remove_pages_artifact_not_found(self) -> None:
        """Test removing pages when artifact doesn't exist."""
        artifact_repo = MockArtifactRepository()
        use_case = RemovePagesUseCase(artifact_repo)

        result = await use_case.execute(uuid4(), [uuid4()])

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"


class TestUpdateTitleMentionUseCase:
    """Test UpdateTitleMentionUseCase."""

    @pytest.mark.asyncio
    async def test_update_title_mention_success(
        self,
        sample_artifact,
        sample_title_mention,
    ) -> None:
        """Test successfully updating title mention."""
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(sample_artifact)

        use_case = UpdateTitleMentionUseCase(artifact_repo)

        result = await use_case.execute(sample_artifact.id, sample_title_mention)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.title_mention == sample_title_mention

    @pytest.mark.asyncio
    async def test_update_title_mention_to_none(
        self,
        sample_artifact,
        sample_title_mention,
    ) -> None:
        """Test updating title mention to None."""
        artifact_repo = MockArtifactRepository()
        sample_artifact.update_title_mention(sample_title_mention)
        artifact_repo.save(sample_artifact)

        use_case = UpdateTitleMentionUseCase(artifact_repo)

        result = await use_case.execute(sample_artifact.id, None)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.title_mention is None

    @pytest.mark.asyncio
    async def test_update_title_mention_artifact_not_found(self) -> None:
        """Test updating title mention when artifact doesn't exist."""
        artifact_repo = MockArtifactRepository()
        use_case = UpdateTitleMentionUseCase(artifact_repo)

        result = await use_case.execute(
            uuid4(),
            TitleMention(title="test", confidence=0.9),
        )

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"


class TestUpdateSummaryCandidateUseCase:
    """Test UpdateSummaryCandidateUseCase."""

    @pytest.mark.asyncio
    async def test_update_summary_candidate_success(
        self,
        sample_artifact,
        sample_summary_candidate,
    ) -> None:
        """Test successfully updating summary candidate."""
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(sample_artifact)

        use_case = UpdateSummaryCandidateUseCase(artifact_repo)

        result = await use_case.execute(sample_artifact.id, sample_summary_candidate)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.summary_candidate == sample_summary_candidate

    @pytest.mark.asyncio
    async def test_update_summary_candidate_artifact_not_found(self) -> None:
        """Test updating summary candidate when artifact doesn't exist."""
        artifact_repo = MockArtifactRepository()
        use_case = UpdateSummaryCandidateUseCase(artifact_repo)

        result = await use_case.execute(
            uuid4(),
            SummaryCandidate(summary="test", page_number=1, confidence=0.9),
        )

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"


class TestUpdateTagsUseCase:
    """Test UpdateTagsUseCase."""

    @pytest.mark.asyncio
    async def test_update_tags_success(self, sample_artifact) -> None:
        """Test successfully updating tags."""
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(sample_artifact)

        tags = ["chemistry", "research"]
        use_case = UpdateTagsUseCase(artifact_repo)

        result = await use_case.execute(sample_artifact.id, tags)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.tags == tags

    @pytest.mark.asyncio
    async def test_update_tags_empty(self, sample_artifact) -> None:
        """Test updating with empty tags."""
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(sample_artifact)

        use_case = UpdateTagsUseCase(artifact_repo)

        result = await use_case.execute(sample_artifact.id, [])

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.tags == []

    @pytest.mark.asyncio
    async def test_update_tags_artifact_not_found(self) -> None:
        """Test updating tags when artifact doesn't exist."""
        artifact_repo = MockArtifactRepository()
        use_case = UpdateTagsUseCase(artifact_repo)

        result = await use_case.execute(uuid4(), ["tag"])

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"


class TestDeleteArtifactUseCase:
    """Test DeleteArtifactUseCase."""

    @pytest.mark.asyncio
    async def test_delete_artifact_success(self, sample_artifact) -> None:
        """Test successfully deleting an artifact."""
        artifact_repo = MockArtifactRepository()
        page_repo = MockPageRepository()

        from domain.aggregates.page import Page

        # Create pages associated with artifact
        page1 = Page.create(name="Page 1", artifact_id=sample_artifact.id)
        page2 = Page.create(name="Page 2", artifact_id=sample_artifact.id)

        sample_artifact.add_pages([page1.id, page2.id])
        artifact_repo.save(sample_artifact)
        page_repo.save(page1)
        page_repo.save(page2)

        use_case = DeleteArtifactUseCase(artifact_repo, page_repo)

        result = await use_case.execute(sample_artifact.id)

        assert isinstance(result, Success)

        # Verify artifact is deleted
        deleted_artifact = artifact_repo.artifacts[sample_artifact.id]
        assert deleted_artifact.is_deleted is True

        # Verify pages are deleted
        assert page_repo.pages[page1.id].is_deleted is True
        assert page_repo.pages[page2.id].is_deleted is True

    @pytest.mark.asyncio
    async def test_delete_artifact_not_found(self) -> None:
        """Test deleting a non-existent artifact."""
        artifact_repo = MockArtifactRepository()
        page_repo = MockPageRepository()
        use_case = DeleteArtifactUseCase(artifact_repo, page_repo)

        result = await use_case.execute(uuid4())

        assert isinstance(result, Failure)
        error = result.failure()
        assert error.category == "not_found"

    @pytest.mark.asyncio
    async def test_delete_artifact_with_external_publisher(self, sample_artifact) -> None:
        """Test deleting artifact with external event publisher."""
        artifact_repo = MockArtifactRepository()
        page_repo = MockPageRepository()
        publisher = MockExternalEventPublisher()

        artifact_repo.save(sample_artifact)
        use_case = DeleteArtifactUseCase(artifact_repo, page_repo, publisher)

        result = await use_case.execute(sample_artifact.id)

        assert isinstance(result, Success)
        assert publisher.artifact_deleted_called is True
