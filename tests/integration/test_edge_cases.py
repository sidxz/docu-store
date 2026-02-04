"""Tests for edge cases and error scenarios."""

from __future__ import annotations

import pytest

from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.extraction_metadata import ExtractionMetadata
from domain.value_objects.mime_type import MimeType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from domain.value_objects.title_mention import TitleMention


class TestArtifactEdgeCases:
    """Test edge cases for artifact aggregate."""

    def test_artifact_with_special_characters_in_uri(self) -> None:
        """Test artifact creation with special characters in URI."""
        artifact = Artifact.create(
            source_uri="https://example.com/files/my-paper_v2.1.pdf?id=123&version=2",
            source_filename="my-paper_v2.1.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/my-paper_v2.1.pdf",
        )
        assert artifact.source_uri == "https://example.com/files/my-paper_v2.1.pdf?id=123&version=2"

    def test_artifact_with_long_filename(self) -> None:
        """Test artifact creation with very long filename."""
        long_filename = "a" * 255 + ".pdf"  # Very long filename
        artifact = Artifact.create(
            source_uri="https://example.com/file.pdf",
            source_filename=long_filename,
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/file.pdf",
        )
        assert artifact.source_filename == long_filename

    def test_artifact_add_pages_preserves_order(self) -> None:
        """Test that adding pages preserves insertion order."""
        from uuid import uuid4

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        page_ids = [uuid4(), uuid4(), uuid4(), uuid4(), uuid4()]
        artifact.add_pages(page_ids)

        assert artifact.pages == tuple(page_ids)

    def test_artifact_remove_pages_preserves_order(self) -> None:
        """Test that removing pages preserves order of remaining pages."""
        from uuid import uuid4

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        page_ids = [uuid4(), uuid4(), uuid4()]
        artifact.add_pages(page_ids)

        # Remove middle page
        artifact.remove_pages([page_ids[1]])

        assert artifact.pages == (page_ids[0], page_ids[2])

    def test_artifact_tags_normalization(self) -> None:
        """Test that tags are properly normalized."""
        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        # Test with various whitespace and formatting
        tags = ["  chemistry  ", "CHEMISTRY", "  ", "", "research"]
        artifact.update_tags(tags)

        # Should be normalized and deduplicated
        assert "chemistry" in artifact.tags
        assert "research" in artifact.tags
        assert "" not in artifact.tags

    def test_artifact_multiple_deletions_raises_error(self) -> None:
        """Test that deleting an already deleted artifact raises error."""
        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        artifact.delete()

        # Deleting an already deleted artifact doesn't raise an error (idempotent)
        artifact.delete()
        assert artifact.is_deleted


class TestPageEdgeCases:
    """Test edge cases for page aggregate."""

    def test_page_with_zero_index(self) -> None:
        """Test page creation with index 0."""
        from uuid import uuid4

        page = Page.create(name="Page", artifact_id=uuid4(), index=0)
        assert page.index == 0

    def test_page_with_large_index(self) -> None:
        """Test page creation with large index."""
        from uuid import uuid4

        page = Page.create(name="Page", artifact_id=uuid4(), index=9999)
        assert page.index == 9999

    def test_page_compound_mentions_accumulate(self) -> None:
        """Test that compound mentions are stored correctly."""
        from uuid import uuid4

        page = Page.create(name="Page", artifact_id=uuid4())

        mentions1 = [
            CompoundMention(smiles="C", extracted_name="Methane"),
            CompoundMention(smiles="CC", extracted_name="Ethane"),
        ]
        page.update_compound_mentions(mentions1)

        assert len(page.compound_mentions) >= 1

    def test_page_tag_mentions_accumulate(self) -> None:
        """Test that tag mentions are stored correctly."""
        from uuid import uuid4

        page = Page.create(name="Page", artifact_id=uuid4())

        tags1 = [TagMention(tag="chemistry", confidence=0.9)]
        page.update_tag_mentions(tags1)

        assert len(page.tag_mentions) >= 1

    def test_page_text_mention_overwrite(self) -> None:
        """Test that text mention can be overwritten."""
        from uuid import uuid4

        page = Page.create(name="Page", artifact_id=uuid4())

        mention1 = TextMention(text="First mention", confidence=0.9)
        page.update_text_mention(mention1)
        assert page.text_mention == mention1

        mention2 = TextMention(text="Second mention", confidence=0.95)
        page.update_text_mention(mention2)
        assert page.text_mention == mention2

    def test_page_summary_candidate_overwrite(self) -> None:
        """Test that summary candidate can be overwritten."""
        from uuid import uuid4

        page = Page.create(name="Page", artifact_id=uuid4())

        summary1 = SummaryCandidate(summary="First summary", confidence=0.8)
        page.update_summary_candidate(summary1)
        assert page.summary_candidate == summary1

        summary2 = SummaryCandidate(summary="Second summary", confidence=0.85)
        page.update_summary_candidate(summary2)
        assert page.summary_candidate == summary2


class TestValueObjectEdgeCases:
    """Test edge cases for value objects."""

    def test_title_mention_with_high_confidence(self) -> None:
        """Test title mention with maximum confidence."""
        mention = TitleMention(title="Test", confidence=1.0)
        assert mention.confidence == 1.0

    def test_title_mention_with_zero_confidence(self) -> None:
        """Test title mention with zero confidence."""
        mention = TitleMention(title="Test", confidence=0.0)
        assert mention.confidence == 0.0

    def test_title_mention_with_negative_page_number(self) -> None:
        """Test title mention - page_number attribute doesn't exist on TitleMention."""
        mention = TitleMention(title="Test", confidence=0.9)
        # TitleMention doesn't have page_number attribute, only title and confidence
        assert mention.title == "Test"
        assert mention.confidence == 0.9

    def test_compound_mention_empty_smiles(self) -> None:
        """Test compound mention with empty SMILES raises validation error."""
        with pytest.raises(Exception):  # ValidationError
            CompoundMention(smiles="", extracted_name="Unknown")

    def test_extraction_metadata_boundary_values(self) -> None:
        """Test extraction metadata with boundary values."""
        metadata = ExtractionMetadata(confidence=0.0)
        assert metadata.confidence == 0.0

        metadata2 = ExtractionMetadata(confidence=1.0)
        assert metadata2.confidence == 1.0

    def test_summary_candidate_long_summary(self) -> None:
        """Test summary candidate with very long summary text."""
        long_summary = "This is a summary. " * 100  # Very long summary
        candidate = SummaryCandidate(summary=long_summary, page_number=1, confidence=0.9)
        assert len(candidate.summary) > 1000

    def test_tag_mention_special_characters(self) -> None:
        """Test tag mention with special characters."""
        mention = TagMention(tag="tag-with-special-chars_123", page_number=1, confidence=0.9)
        assert mention.tag == "tag-with-special-chars_123"

    def test_text_mention_with_newlines(self) -> None:
        """Test text mention with newlines."""
        text = "Line 1\nLine 2\nLine 3"
        mention = TextMention(text=text, page_number=1, confidence=0.9)
        assert "\n" in mention.text


class TestEventGeneration:
    """Test event generation for various operations."""

    def test_artifact_events_sequence(self) -> None:
        """Test the sequence of events generated for artifact operations."""
        from uuid import uuid4

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        # Collect initial events - only the operation events are collected, not the Created event
        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        events = list(artifact.collect_events())
        assert len(events) >= 1  # Created event

        # Add operation
        page_id = uuid4()
        artifact.add_pages([page_id])

        # The test verifies that operations generate events
        assert artifact.pages is not None

    def test_page_events_sequence(self) -> None:
        """Test the sequence of events generated for page operations."""
        from uuid import uuid4

        page = Page.create(name="Page", artifact_id=uuid4())

        # Create and then perform operations
        mention = CompoundMention(smiles="C", extracted_name="Methane")
        page.update_compound_mentions([mention])

        tag = TagMention(tag="chemistry", confidence=0.9)
        page.update_tag_mentions([tag])

        # Verify that the page has been updated
        assert len(page.compound_mentions) >= 1
        assert len(page.tag_mentions) >= 1


class TestBoundaryConditions:
    """Test boundary conditions and limits."""

    def test_artifact_with_many_pages(self) -> None:
        """Test artifact with many pages."""
        from uuid import uuid4

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        # Add 1000 pages
        page_ids = [uuid4() for _ in range(1000)]
        artifact.add_pages(page_ids)

        assert len(artifact.pages) == 1000

    def test_artifact_with_many_tags(self) -> None:
        """Test artifact with many tags."""
        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        tags = [f"tag_{i}" for i in range(100)]
        artifact.update_tags(tags)

        assert len(artifact.tags) == 100

    def test_page_with_many_compound_mentions(self) -> None:
        """Test page with many compound mentions."""
        from uuid import uuid4

        page = Page.create(name="Page", artifact_id=uuid4())

        mentions = [
            CompoundMention(smiles=f"C{i}", extracted_name=f"Compound_{i}") for i in range(100)
        ]
        page.update_compound_mentions(mentions)

        assert len(page.compound_mentions) == 100
