"""Comprehensive integration tests."""

from __future__ import annotations

import pytest
from returns.result import Success

from application.dtos.artifact_dtos import CreateArtifactRequest
from application.use_cases.artifact_use_cases import (
    CreateArtifactUseCase,
    DeleteArtifactUseCase,
    UpdateTagsUseCase,
    UpdateTitleMentionUseCase,
)
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.title_mention import TitleMention
from tests.mocks import MockArtifactRepository, MockExternalEventPublisher, MockPageRepository


class TestArtifactLifecycle:
    """Test complete artifact lifecycle."""

    @pytest.mark.asyncio
    async def test_full_artifact_workflow(self) -> None:
        """Test full artifact workflow from creation to updates."""
        # Setup repositories
        artifact_repo = MockArtifactRepository()
        page_repo = MockPageRepository()
        publisher = MockExternalEventPublisher()

        # Create artifact
        create_artifact_use_case = CreateArtifactUseCase(artifact_repo, publisher)
        artifact_request = CreateArtifactRequest(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        create_result = await create_artifact_use_case.execute(artifact_request)
        assert isinstance(create_result, Success)
        artifact_response = create_result.unwrap()
        artifact_id = artifact_response.artifact_id

        # Update title mention
        update_title_use_case = UpdateTitleMentionUseCase(artifact_repo, publisher)
        title_mention = TitleMention(title="Research Paper 2024", confidence=0.95)
        title_result = await update_title_use_case.execute(artifact_id, title_mention)
        assert isinstance(title_result, Success)

        # Update tags
        update_tags_use_case = UpdateTagsUseCase(artifact_repo, publisher)
        tags_result = await update_tags_use_case.execute(artifact_id, ["chemistry", "research"])
        assert isinstance(tags_result, Success)
        tags_response = tags_result.unwrap()
        assert tags_response.tags == ["chemistry", "research"]

        # Verify artifact state
        final_artifact = artifact_repo.get_by_id(artifact_id)
        assert final_artifact.title_mention == title_mention
        assert final_artifact.tags == ["chemistry", "research"]

    @pytest.mark.asyncio
    async def test_artifact_with_pages_workflow(self) -> None:
        """Test artifact creation and page association workflow."""
        artifact_repo = MockArtifactRepository()
        page_repo = MockPageRepository()

        # Create artifact
        create_artifact_use_case = CreateArtifactUseCase(artifact_repo)
        artifact_request = CreateArtifactRequest(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        create_result = await create_artifact_use_case.execute(artifact_request)
        assert isinstance(create_result, Success)
        artifact_id = create_result.unwrap().artifact_id

        # Create pages for artifact
        from domain.aggregates.page import Page

        page1 = Page.create(name="Introduction", artifact_id=artifact_id, index=0)
        page2 = Page.create(name="Methods", artifact_id=artifact_id, index=1)

        page_repo.save(page1)
        page_repo.save(page2)

        # Add pages to artifact
        from application.use_cases.artifact_use_cases import AddPagesUseCase

        add_pages_use_case = AddPagesUseCase(artifact_repo, page_repo)
        add_result = await add_pages_use_case.execute(artifact_id, [page1.id, page2.id])

        assert isinstance(add_result, Success)
        response = add_result.unwrap()
        assert len(response.pages) == 2

    @pytest.mark.asyncio
    async def test_artifact_deletion_cascade(self) -> None:
        """Test that deleting artifact cascades to pages."""
        artifact_repo = MockArtifactRepository()
        page_repo = MockPageRepository()
        publisher = MockExternalEventPublisher()

        # Create artifact
        from domain.aggregates.artifact import Artifact

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        artifact_repo.save(artifact)

        # Create and save pages
        from domain.aggregates.page import Page

        page1 = Page.create(name="Page 1", artifact_id=artifact.id)
        page2 = Page.create(name="Page 2", artifact_id=artifact.id)

        artifact.add_pages([page1.id, page2.id])
        artifact_repo.save(artifact)
        page_repo.save(page1)
        page_repo.save(page2)

        # Delete artifact
        delete_use_case = DeleteArtifactUseCase(artifact_repo, page_repo, publisher)
        delete_result = await delete_use_case.execute(artifact.id)

        assert isinstance(delete_result, Success)

        # Verify artifact is deleted
        deleted_artifact = artifact_repo.get_by_id(artifact.id)
        assert deleted_artifact.is_deleted is True

        # Verify pages are deleted
        deleted_page1 = page_repo.get_by_id(page1.id)
        deleted_page2 = page_repo.get_by_id(page2.id)
        assert deleted_page1.is_deleted is True
        assert deleted_page2.is_deleted is True

        # Verify publisher was notified
        assert publisher.artifact_deleted_called is True


class TestPageLifecycle:
    """Test complete page lifecycle."""

    @pytest.mark.asyncio
    async def test_full_page_workflow(self, sample_artifact_id) -> None:
        """Test full page workflow from creation to updates."""
        page_repo = MockPageRepository()
        artifact_repo = MockArtifactRepository()

        # Create page
        from domain.aggregates.page import Page

        page = Page.create(name="Introduction", artifact_id=sample_artifact_id, index=0)
        page_repo.save(page)

        # Update with compound mentions
        from domain.value_objects.compound_mention import CompoundMention

        mention = CompoundMention(smiles="C1=CC=CC=C1", extracted_name="Benzene")
        page.update_compound_mentions([mention])
        page_repo.save(page)

        # Update with tag mentions
        from domain.value_objects.tag_mention import TagMention

        tag = TagMention(tag="chemistry", page_number=1, confidence=0.88)
        page.update_tag_mentions([tag])
        page_repo.save(page)

        # Update with summary candidate
        from domain.value_objects.summary_candidate import SummaryCandidate

        summary = SummaryCandidate(summary="This page discusses...", page_number=1, confidence=0.85)
        page.update_summary_candidate(summary)
        page_repo.save(page)

        # Verify final state
        retrieved_page = page_repo.get_by_id(page.id)
        assert len(retrieved_page.compound_mentions) == 1
        assert len(retrieved_page.tag_mentions) == 1
        assert retrieved_page.summary_candidate == summary


class TestConcurrentOperations:
    """Test concurrent operations on aggregates."""

    @pytest.mark.asyncio
    async def test_concurrent_updates(self) -> None:
        """Test that concurrent updates work correctly."""
        from domain.aggregates.artifact import Artifact

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        # Apply multiple updates
        artifact.update_tags(["tag1", "tag2"])
        artifact.update_tags(["tag1", "tag2", "tag3"])

        title = TitleMention(title="Title", confidence=0.9)
        artifact.update_title_mention(title)

        # Verify final state
        assert len(artifact.tags) == 3
        assert artifact.title_mention == title


class TestErrorRecovery:
    """Test error recovery scenarios."""

    @pytest.mark.asyncio
    async def test_recover_from_not_found_error(self) -> None:
        """Test recovering from not found error."""
        artifact_repo = MockArtifactRepository()
        use_case = UpdateTitleMentionUseCase(artifact_repo)

        from uuid import uuid4

        result = await use_case.execute(
            uuid4(),
            TitleMention(title="test", confidence=0.9),
        )

        from returns.result import Failure

        assert isinstance(result, Failure)

        # Subsequent operation should work fine
        from domain.aggregates.artifact import Artifact

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        artifact_repo.save(artifact)

        result2 = await use_case.execute(
            artifact.id,
            TitleMention(title="test", confidence=0.9),
        )
        assert isinstance(result2, Success)


class TestDataConsistency:
    """Test data consistency across operations."""

    @pytest.mark.asyncio
    async def test_consistency_across_updates(self) -> None:
        """Test that data remains consistent across multiple updates."""
        artifact_repo = MockArtifactRepository()

        from domain.aggregates.artifact import Artifact

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        artifact_repo.save(artifact)

        # Apply various updates
        from uuid import uuid4

        page_ids = [uuid4(), uuid4()]
        artifact.add_pages(page_ids)
        artifact_repo.save(artifact)

        artifact.update_tags(["tag1"])
        artifact_repo.save(artifact)

        artifact.update_tags(["tag1", "tag2"])
        artifact_repo.save(artifact)

        # Verify consistency
        retrieved = artifact_repo.get_by_id(artifact.id)
        assert retrieved.pages == tuple(page_ids)
        assert retrieved.tags == ["tag1", "tag2"]
        assert retrieved.source_uri == artifact.source_uri
