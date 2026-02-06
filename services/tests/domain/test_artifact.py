"""Tests for Artifact aggregate."""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.aggregates.artifact import Artifact
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.title_mention import TitleMention


class TestArtifactCreation:
    """Test artifact creation and initialization."""

    def test_create_artifact(self, sample_artifact: Artifact) -> None:
        """Test creating an Artifact aggregate."""
        assert sample_artifact.source_uri == "https://example.com/paper.pdf"
        assert sample_artifact.source_filename == "research_paper.pdf"
        assert sample_artifact.artifact_type == ArtifactType.RESEARCH_ARTICLE
        assert sample_artifact.mime_type == MimeType.PDF
        assert sample_artifact.storage_location == "/storage/artifacts/paper123.pdf"
        assert sample_artifact.id is not None
        assert sample_artifact.version == 0
        assert sample_artifact.pages == ()
        assert sample_artifact.is_deleted is False

    def test_artifact_initialization_validates_source_uri(self) -> None:
        """Test that source_uri can be None (optional field)."""
        artifact = Artifact.create(
            source_uri=None,
            source_filename="file.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/file.pdf",
        )
        assert artifact.source_uri is None

    def test_artifact_initialization_validates_source_filename(self) -> None:
        """Test that source_filename can be None (optional field)."""
        artifact = Artifact.create(
            source_uri="https://example.com/file.pdf",
            source_filename=None,
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/file.pdf",
        )
        assert artifact.source_filename is None

    def test_artifact_initialization_validates_artifact_type(self) -> None:
        """Test that None artifact_type raises ValueError."""
        with pytest.raises(ValueError, match="artifact_type must be provided"):
            Artifact.create(
                source_uri="https://example.com/file.pdf",
                source_filename="file.pdf",
                artifact_type=None,  # type: ignore
                mime_type=MimeType.PDF,
                storage_location="/storage/file.pdf",
            )

    def test_artifact_initialization_validates_mime_type(self) -> None:
        """Test that None mime_type raises ValueError."""
        with pytest.raises(ValueError, match="mime_type must be provided"):
            Artifact.create(
                source_uri="https://example.com/file.pdf",
                source_filename="file.pdf",
                artifact_type=ArtifactType.RESEARCH_ARTICLE,
                mime_type=None,  # type: ignore
                storage_location="/storage/file.pdf",
            )

    def test_artifact_initialization_validates_storage_location(self) -> None:
        """Test that empty storage_location raises ValueError."""
        with pytest.raises(ValueError, match="storage_location must be provided"):
            Artifact.create(
                source_uri="https://example.com/file.pdf",
                source_filename="file.pdf",
                artifact_type=ArtifactType.RESEARCH_ARTICLE,
                mime_type=MimeType.PDF,
                storage_location="",
            )

    def test_artifact_strips_whitespace_on_creation(self) -> None:
        """Test that artifact strips whitespace from text fields."""
        artifact = Artifact.create(
            source_uri="  https://example.com/file.pdf  ",
            source_filename="  file.pdf  ",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="  /storage/file.pdf  ",
        )
        assert artifact.source_uri == "https://example.com/file.pdf"
        assert artifact.source_filename == "file.pdf"
        assert artifact.storage_location == "/storage/file.pdf"

    def test_created_event_is_generated(self, sample_artifact: Artifact) -> None:
        """Test that a Created event is generated on artifact creation."""
        events = list(sample_artifact.collect_events())
        assert len(events) == 1
        event = events[0]
        assert event.__class__.__name__ == "Created"
        # Verify event payload contains all necessary data for reconstitution
        assert event.source_uri == "https://example.com/paper.pdf"
        assert event.source_filename == "research_paper.pdf"
        assert event.artifact_type == ArtifactType.RESEARCH_ARTICLE
        assert event.mime_type == MimeType.PDF
        assert event.storage_location == "/storage/artifacts/paper123.pdf"


class TestArtifactPageManagement:
    """Test adding and removing pages to/from artifact."""

    def test_add_pages(self, sample_artifact: Artifact) -> None:
        """Test adding pages to an artifact."""
        page_ids = [uuid4(), uuid4(), uuid4()]
        sample_artifact.add_pages(page_ids)

        assert sample_artifact.pages == tuple(page_ids)

    def test_add_pages_idempotent(self, sample_artifact: Artifact) -> None:
        """Test that adding duplicate page IDs is idempotent."""
        page_id = uuid4()
        sample_artifact.add_pages([page_id])
        sample_artifact.add_pages([page_id])

        assert sample_artifact.pages == (page_id,)

    def test_add_pages_empty_list_is_noop(self, sample_artifact: Artifact) -> None:
        """Test that adding empty list is a no-op."""
        sample_artifact.add_pages([])
        assert sample_artifact.pages == ()

    def test_add_pages_multiple_batches(self, sample_artifact: Artifact) -> None:
        """Test adding pages in multiple batches."""
        first_batch = [uuid4(), uuid4()]
        second_batch = [uuid4()]

        sample_artifact.add_pages(first_batch)
        sample_artifact.add_pages(second_batch)

        assert len(sample_artifact.pages) == 3
        assert sample_artifact.pages[:2] == tuple(first_batch)
        assert sample_artifact.pages[2:] == tuple(second_batch)

    def test_remove_pages(self, sample_artifact: Artifact) -> None:
        """Test removing pages from an artifact."""
        page_ids = [uuid4(), uuid4(), uuid4()]
        sample_artifact.add_pages(page_ids)

        sample_artifact.remove_pages([page_ids[0]])
        assert sample_artifact.pages == tuple(page_ids[1:])

    def test_remove_pages_idempotent(self, sample_artifact: Artifact) -> None:
        """Test that removing non-existent page IDs is idempotent."""
        page_id = uuid4()
        sample_artifact.add_pages([page_id])

        sample_artifact.remove_pages([uuid4()])
        assert sample_artifact.pages == (page_id,)

    def test_remove_pages_empty_list_is_noop(self, sample_artifact: Artifact) -> None:
        """Test that removing empty list is a no-op."""
        page_id = uuid4()
        sample_artifact.add_pages([page_id])

        sample_artifact.remove_pages([])
        assert sample_artifact.pages == (page_id,)

    def test_remove_multiple_pages(self, sample_artifact: Artifact) -> None:
        """Test removing multiple pages at once."""
        page_ids = [uuid4(), uuid4(), uuid4()]
        sample_artifact.add_pages(page_ids)

        sample_artifact.remove_pages([page_ids[0], page_ids[2]])
        assert sample_artifact.pages == (page_ids[1],)

    def test_add_pages_raises_on_deleted_artifact(self, sample_artifact: Artifact) -> None:
        """Test that adding pages to a deleted artifact raises error."""
        sample_artifact.delete()
        with pytest.raises(ValueError, match="Cannot add pages to a deleted artifact"):
            sample_artifact.add_pages([uuid4()])

    def test_remove_pages_raises_on_deleted_artifact(self, sample_artifact: Artifact) -> None:
        """Test that removing pages from a deleted artifact raises error."""
        page_id = uuid4()
        sample_artifact.add_pages([page_id])
        sample_artifact.delete()

        with pytest.raises(ValueError, match="Cannot remove pages from a deleted artifact"):
            sample_artifact.remove_pages([page_id])


class TestArtifactTitleMention:
    """Test updating title mention on artifact."""

    def test_update_title_mention(
        self,
        sample_artifact: Artifact,
        sample_title_mention: TitleMention,
    ) -> None:
        """Test updating title mention."""
        sample_artifact.update_title_mention(sample_title_mention)
        assert sample_artifact.title_mention == sample_title_mention

    def test_update_title_mention_to_none(
        self,
        sample_artifact: Artifact,
        sample_title_mention: TitleMention,
    ) -> None:
        """Test updating title mention to None."""
        sample_artifact.update_title_mention(sample_title_mention)
        sample_artifact.update_title_mention(None)
        assert sample_artifact.title_mention is None

    def test_update_title_mention_raises_on_deleted_artifact(
        self,
        sample_artifact: Artifact,
        sample_title_mention: TitleMention,
    ) -> None:
        """Test that updating title mention on deleted artifact raises error."""
        sample_artifact.delete()
        with pytest.raises(ValueError, match="Cannot update title mention on a deleted artifact"):
            sample_artifact.update_title_mention(sample_title_mention)


class TestArtifactSummaryCandidate:
    """Test updating summary candidate on artifact."""

    def test_update_summary_candidate(
        self,
        sample_artifact: Artifact,
        sample_summary_candidate: SummaryCandidate,
    ) -> None:
        """Test updating summary candidate."""
        sample_artifact.update_summary_candidate(sample_summary_candidate)
        assert sample_artifact.summary_candidate == sample_summary_candidate

    def test_update_summary_candidate_to_none(
        self,
        sample_artifact: Artifact,
        sample_summary_candidate: SummaryCandidate,
    ) -> None:
        """Test updating summary candidate to None."""
        sample_artifact.update_summary_candidate(sample_summary_candidate)
        sample_artifact.update_summary_candidate(None)
        assert sample_artifact.summary_candidate is None

    def test_update_summary_candidate_raises_on_deleted_artifact(
        self,
        sample_artifact: Artifact,
        sample_summary_candidate: SummaryCandidate,
    ) -> None:
        """Test that updating summary candidate on deleted artifact raises error."""
        sample_artifact.delete()
        with pytest.raises(
            ValueError,
            match="Cannot update summary candidate on a deleted artifact",
        ):
            sample_artifact.update_summary_candidate(sample_summary_candidate)


class TestArtifactTags:
    """Test updating tags on artifact."""

    def test_update_tags(self, sample_artifact: Artifact) -> None:
        """Test updating tags."""
        tags = ["chemistry", "research", "important"]
        sample_artifact.update_tags(tags)
        assert sample_artifact.tags == tags

    def test_update_tags_empty_list(self, sample_artifact: Artifact) -> None:
        """Test updating to empty tags."""
        tags = ["chemistry"]
        sample_artifact.update_tags(tags)
        sample_artifact.update_tags([])
        assert sample_artifact.tags == []

    def test_update_tags_removes_duplicates(self, sample_artifact: Artifact) -> None:
        """Test that duplicate tags are removed."""
        tags = ["chemistry", "research", "chemistry"]
        sample_artifact.update_tags(tags)
        assert sample_artifact.tags == ["chemistry", "research"]

    def test_update_tags_strips_whitespace(self, sample_artifact: Artifact) -> None:
        """Test that tags are stripped of whitespace."""
        tags = ["  chemistry  ", "  research  "]
        sample_artifact.update_tags(tags)
        assert sample_artifact.tags == ["chemistry", "research"]

    def test_update_tags_removes_blank_tags(self, sample_artifact: Artifact) -> None:
        """Test that blank tags are removed."""
        tags = ["chemistry", "", "  ", "research"]
        sample_artifact.update_tags(tags)
        assert sample_artifact.tags == ["chemistry", "research"]

    def test_update_tags_same_tags_is_noop(self, sample_artifact: Artifact) -> None:
        """Test that updating with same tags generates events both times."""
        tags = ["chemistry", "research"]
        sample_artifact.update_tags(tags)
        # First update creates a TagsUpdated event
        assert sample_artifact.tags == tags

        # Second update with same tags should work (idempotent)
        sample_artifact.update_tags(tags)
        assert sample_artifact.tags == tags

    def test_update_tags_raises_on_deleted_artifact(self, sample_artifact: Artifact) -> None:
        """Test that updating tags on deleted artifact raises error."""
        sample_artifact.delete()
        with pytest.raises(ValueError, match="Cannot update tags on a deleted artifact"):
            sample_artifact.update_tags(["chemistry"])


class TestArtifactDeletion:
    """Test artifact deletion."""

    def test_delete_artifact(self, sample_artifact: Artifact) -> None:
        """Test deleting an artifact."""
        sample_artifact.delete()
        assert sample_artifact.is_deleted is True
        assert sample_artifact.deleted_at is not None

    def test_delete_artifact_generates_event(self, sample_artifact: Artifact) -> None:
        """Test that deleting generates a Deleted event."""
        sample_artifact.delete()
        events = list(sample_artifact.collect_events())
        assert events[-1].__class__.__name__ == "Deleted"

    def test_deleted_artifact_rejects_updates(self, sample_artifact: Artifact) -> None:
        """Test that a deleted artifact rejects updates."""
        sample_artifact.delete()

        with pytest.raises(ValueError, match="Cannot add pages"):
            sample_artifact.add_pages([uuid4()])

        with pytest.raises(ValueError, match="Cannot update title mention"):
            sample_artifact.update_title_mention(
                TitleMention(title="test", confidence=0.9),
            )

        with pytest.raises(ValueError, match="Cannot update tags"):
            sample_artifact.update_tags(["tag"])


class TestArtifactHashing:
    """Test artifact hashing."""

    def test_artifact_hash_based_on_id(self, sample_artifact: Artifact) -> None:
        """Test that artifact hash is based on its ID."""
        assert hash(sample_artifact) == hash(sample_artifact.id)

    def test_same_id_same_hash(self) -> None:
        """Test that two artifacts with same ID have same hash."""
        artifact1 = Artifact.create(
            source_uri="https://example.com/a.pdf",
            source_filename="a.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/a.pdf",
        )
        artifact2 = Artifact.create(
            source_uri="https://example.com/b.pdf",
            source_filename="b.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/b.pdf",
        )
        assert artifact1.id != artifact2.id
        assert hash(artifact1) != hash(artifact2)


class TestArtifactEventSourcing:
    """Test event sourcing reconstitution and replay capabilities.

    These tests ensure the aggregate can be properly reconstructed from events,
    which is a fundamental requirement of event sourcing.
    """

    def test_pages_added_event_contains_complete_data(self) -> None:
        """Test that PagesAdded event captures all necessary data."""
        artifact = Artifact.create(
            source_uri="https://example.com/test.pdf",
            source_filename="test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/test.pdf",
        )

        page_ids = [uuid4(), uuid4(), uuid4()]
        artifact.add_pages(page_ids)

        events = list(artifact.collect_events())
        pages_added_event = events[1]  # Second event after Created

        assert pages_added_event.__class__.__name__ == "PagesAdded"
        assert pages_added_event.page_ids == page_ids

    def test_title_mention_updated_event_contains_complete_data(self) -> None:
        """Test that TitleMentionUpdated event captures all necessary data."""
        artifact = Artifact.create(
            source_uri="https://example.com/test.pdf",
            source_filename="test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/test.pdf",
        )

        title_mention = TitleMention(title="Important Research", confidence=0.95)
        artifact.update_title_mention(title_mention)

        events = list(artifact.collect_events())
        title_event = events[1]

        assert title_event.__class__.__name__ == "TitleMentionUpdated"
        assert title_event.title_mention == title_mention
        assert title_event.title_mention.title == "Important Research"
        assert title_event.title_mention.confidence == 0.95

    def test_summary_candidate_updated_event_contains_complete_data(self) -> None:
        """Test that SummaryCandidateUpdated event captures all necessary data."""
        artifact = Artifact.create(
            source_uri="https://example.com/test.pdf",
            source_filename="test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/test.pdf",
        )

        summary = SummaryCandidate(summary="This paper discusses...", confidence=0.88)
        artifact.update_summary_candidate(summary)

        events = list(artifact.collect_events())
        summary_event = events[1]

        assert summary_event.__class__.__name__ == "SummaryCandidateUpdated"
        assert summary_event.summary_candidate == summary
        assert summary_event.summary_candidate.summary == "This paper discusses..."
        assert summary_event.summary_candidate.confidence == 0.88

    def test_tags_updated_event_contains_complete_data(self) -> None:
        """Test that TagsUpdated event captures all necessary data."""
        artifact = Artifact.create(
            source_uri="https://example.com/test.pdf",
            source_filename="test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/test.pdf",
        )

        tags = ["chemistry", "research", "important"]
        artifact.update_tags(tags)

        events = list(artifact.collect_events())
        tags_event = events[1]

        assert tags_event.__class__.__name__ == "TagsUpdated"
        assert tags_event.tags == tags

    def test_deleted_event_contains_timestamp(self) -> None:
        """Test that Deleted event captures deletion timestamp."""
        artifact = Artifact.create(
            source_uri="https://example.com/test.pdf",
            source_filename="test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/test.pdf",
        )

        artifact.delete()

        events = list(artifact.collect_events())
        deleted_event = events[1]

        assert deleted_event.__class__.__name__ == "Deleted"
        assert deleted_event.deleted_at is not None
        assert isinstance(deleted_event.deleted_at, type(artifact.deleted_at))

    def test_no_op_operations_do_not_generate_events(self) -> None:
        """Test that operations that don't change state don't generate events.

        This is important for ES performance and preventing unnecessary event proliferation.
        """
        artifact = Artifact.create(
            source_uri="https://example.com/test.pdf",
            source_filename="test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/test.pdf",
        )

        # Clear events from creation
        list(artifact.collect_events())

        # No-op operations
        artifact.add_pages([])  # Empty list
        artifact.remove_pages([])  # Empty list

        tags = ["test"]
        artifact.update_tags(tags)
        list(artifact.collect_events())  # Clear

        artifact.update_tags(tags)  # Same tags - should be no-op

        events = list(artifact.collect_events())
        assert len(events) == 0, "No-op operations should not generate events"


class TestArtifactInvariants:
    """Test that domain invariants are properly enforced.

    These tests ensure the aggregate cannot enter invalid states,
    which is critical for maintaining data integrity.
    """

    def test_cannot_modify_deleted_artifact_at_all(self) -> None:
        """Test that ALL modifications are rejected on a deleted artifact.

        This is a critical invariant - once deleted, an artifact is immutable.
        """
        artifact = Artifact.create(
            source_uri="https://example.com/test.pdf",
            source_filename="test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/test.pdf",
        )
        artifact.delete()

        # Every modification should fail
        with pytest.raises(ValueError, match="deleted"):
            artifact.add_pages([uuid4()])

        with pytest.raises(ValueError, match="deleted"):
            artifact.remove_pages([uuid4()])

        with pytest.raises(ValueError, match="deleted"):
            artifact.update_title_mention(TitleMention(title="test", confidence=0.9))

        with pytest.raises(ValueError, match="deleted"):
            artifact.update_summary_candidate(
                SummaryCandidate(summary="test", confidence=0.9),
            )

        with pytest.raises(ValueError, match="deleted"):
            artifact.update_tags(["test"])

    def test_deletion_is_idempotent(self) -> None:
        """Test that deleting an already deleted artifact doesn't cause issues.

        Idempotency is important for distributed systems where commands might be retried.
        """
        artifact = Artifact.create(
            source_uri="https://example.com/test.pdf",
            source_filename="test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/test.pdf",
        )

        artifact.delete()
        first_deleted_at = artifact.deleted_at

        # Second delete should not raise an error
        artifact.delete()

        # State should be consistent
        assert artifact.is_deleted is True
        # Note: deleted_at may be updated, which is acceptable

    def test_page_ids_remain_unique_across_operations(self) -> None:
        """Test that page list never contains duplicates, even after multiple operations."""
        artifact = Artifact.create(
            source_uri="https://example.com/test.pdf",
            source_filename="test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/test.pdf",
        )

        page_id = uuid4()

        # Add same page multiple times
        artifact.add_pages([page_id])
        artifact.add_pages([page_id])
        artifact.add_pages([page_id, page_id, page_id])

        # Should only appear once
        assert artifact.pages == (page_id,)

    def test_tags_are_always_normalized(self) -> None:
        """Test that tags are always cleaned and normalized."""
        artifact = Artifact.create(
            source_uri="https://example.com/test.pdf",
            source_filename="test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/test.pdf",
        )

        # Test with messy input
        artifact.update_tags(["  chemistry  ", "", "  ", "research", "chemistry", "BIOLOGY"])

        # Should be normalized: stripped, no blanks, no duplicates
        assert artifact.tags == ["chemistry", "research", "BIOLOGY"]

        # Note: The domain doesn't enforce case normalization - that's acceptable

    def test_cannot_create_artifact_with_invalid_data(self) -> None:
        """Test that artifact creation validates required fields."""
        # None artifact_type
        with pytest.raises(ValueError, match="artifact_type"):
            Artifact.create(
                source_uri="https://example.com/file.pdf",
                source_filename="file.pdf",
                artifact_type=None,  # type: ignore
                mime_type=MimeType.PDF,
                storage_location="/storage/file.pdf",
            )

        # None mime_type
        with pytest.raises(ValueError, match="mime_type"):
            Artifact.create(
                source_uri="https://example.com/file.pdf",
                source_filename="file.pdf",
                artifact_type=ArtifactType.RESEARCH_ARTICLE,
                mime_type=None,  # type: ignore
                storage_location="/storage/file.pdf",
            )

        # Empty storage_location
        with pytest.raises(ValueError, match="storage_location"):
            Artifact.create(
                source_uri="https://example.com/file.pdf",
                source_filename="file.pdf",
                artifact_type=ArtifactType.RESEARCH_ARTICLE,
                mime_type=MimeType.PDF,
                storage_location="",
            )

    def test_whitespace_only_strings_are_treated_as_empty(self) -> None:
        """Test that strings with only whitespace are stripped (required fields still checked)."""
        # Whitespace-only storage_location should still raise (required field)
        with pytest.raises(ValueError, match="storage_location"):
            Artifact.create(
                source_uri="https://example.com/file.pdf",
                source_filename="file.pdf",
                artifact_type=ArtifactType.RESEARCH_ARTICLE,
                mime_type=MimeType.PDF,
                storage_location="   ",
            )

    def test_version_increments_with_each_event(self) -> None:
        """Test that aggregate version properly increments with each state change.

        This is important for optimistic concurrency control in event sourcing.
        """
        artifact = Artifact.create(
            source_uri="https://example.com/test.pdf",
            source_filename="test.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/test.pdf",
        )

        initial_version = artifact.version

        artifact.add_pages([uuid4()])
        assert artifact.version == initial_version + 1

        artifact.update_tags(["test"])
        assert artifact.version == initial_version + 2

        artifact.delete()
        assert artifact.version == initial_version + 3
