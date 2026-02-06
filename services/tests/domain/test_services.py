"""Tests for domain services."""

from __future__ import annotations

from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.services.artifact_deletion_service import ArtifactDeletionService
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType


class TestArtifactDeletionService:
    """Test ArtifactDeletionService domain service."""

    def test_delete_artifact_with_pages(self) -> None:
        """Test deleting an artifact and its associated pages."""
        # Create artifact
        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        # Create pages
        page1 = Page.create(name="Page 1", artifact_id=artifact.id, index=0)
        page2 = Page.create(name="Page 2", artifact_id=artifact.id, index=1)

        # Delete using service
        ArtifactDeletionService.delete_artifact_with_pages(artifact, [page1, page2])

        # Verify artifact is deleted
        assert artifact.is_deleted is True
        assert artifact.deleted_at is not None

        # Verify pages are deleted
        assert page1.is_deleted is True
        assert page1.deleted_at is not None
        assert page2.is_deleted is True
        assert page2.deleted_at is not None

    def test_delete_artifact_with_no_pages(self) -> None:
        """Test deleting an artifact with no associated pages."""
        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        ArtifactDeletionService.delete_artifact_with_pages(artifact, [])

        assert artifact.is_deleted is True

    def test_delete_artifact_generates_events(self) -> None:
        """Test that deletion generates appropriate events."""
        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        page = Page.create(name="Page 1", artifact_id=artifact.id)

        ArtifactDeletionService.delete_artifact_with_pages(artifact, [page])

        # Check artifact events
        artifact_events = list(artifact.collect_events())
        assert artifact_events[-1].__class__.__name__ == "Deleted"

        # Check page events
        page_events = list(page.collect_events())
        assert page_events[-1].__class__.__name__ == "Deleted"

    def test_delete_already_deleted_artifact_raises_error(self) -> None:
        """Test that deleting an already deleted artifact doesn't raise an error."""
        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        artifact.delete()

        # The service should handle already deleted artifacts gracefully
        # without raising an error (idempotent)
        ArtifactDeletionService.delete_artifact_with_pages(artifact, [])

    def test_delete_already_deleted_page_raises_error(self) -> None:
        """Test that deleting an artifact with already deleted pages works."""
        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        page = Page.create(name="Page 1", artifact_id=artifact.id)
        page.delete()

        # The service should handle already deleted pages gracefully
        ArtifactDeletionService.delete_artifact_with_pages(artifact, [page])
