"""Tests for Page aggregate."""

from __future__ import annotations

import pytest

from domain.aggregates.page import Page
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention


class TestPageCreation:
    """Test page creation and initialization."""

    def test_create_page(self, sample_page: Page) -> None:
        """Test creating a Page aggregate."""
        assert sample_page.name == "Introduction"
        assert sample_page.index == 0
        assert sample_page.artifact_id is not None
        assert sample_page.compound_mentions == []
        assert sample_page.tag_mentions == []
        assert sample_page.text_mention is None
        assert sample_page.summary_candidate is None
        assert sample_page.id is not None
        assert sample_page.version == 0
        assert sample_page.is_deleted is False

    def test_create_page_with_custom_index(self, sample_artifact_id: int) -> None:
        """Test creating a page with custom index."""
        page = Page.create(name="Methods", artifact_id=sample_artifact_id, index=5)
        assert page.index == 5

    def test_create_page_default_index(self, sample_artifact_id: int) -> None:
        """Test creating a page with default index."""
        page = Page.create(name="Results", artifact_id=sample_artifact_id)
        assert page.index == 0

    def test_created_event_is_generated(self, sample_page: Page) -> None:
        """Test that a Created event is generated on page creation."""
        events = list(sample_page.collect_events())
        assert len(events) == 1
        event = events[0]
        assert event.__class__.__name__ == "Created"
        # Verify event payload contains all necessary data for reconstitution
        assert event.name == "Introduction"
        assert event.artifact_id is not None
        assert event.index == 0


class TestPageCompoundMentions:
    """Test updating compound mentions on page."""

    def test_add_compound_mentions(
        self,
        sample_page: Page,
        sample_compound_mention: CompoundMention,
    ) -> None:
        """Test adding compound mentions to a page."""
        sample_page.update_compound_mentions([sample_compound_mention])
        assert len(sample_page.compound_mentions) == 1
        assert sample_page.compound_mentions[0].smiles == sample_compound_mention.smiles
        assert (
            sample_page.compound_mentions[0].extracted_name
            == sample_compound_mention.extracted_name
        )

    def test_add_multiple_compound_mentions(self, sample_page: Page) -> None:
        """Test adding multiple compound mentions at once."""
        mentions = [
            CompoundMention(
                smiles="C1=CC=CC=C1",
                extracted_name="Benzene",
                confidence=0.92,
            ),
            CompoundMention(
                smiles="CC(=O)O",
                extracted_name="Acetic Acid",
                confidence=0.88,
            ),
        ]
        sample_page.update_compound_mentions(mentions)
        assert len(sample_page.compound_mentions) == 2
        assert sample_page.compound_mentions[0].extracted_name == "Benzene"
        assert sample_page.compound_mentions[1].extracted_name == "Acetic Acid"

    def test_add_compound_mentions_multiple_times(self, sample_page: Page) -> None:
        """Test that updating compound mentions replaces previous ones (not accumulates)."""
        first_mention = CompoundMention(
            smiles="C1=CC=CC=C1",
            extracted_name="Benzene",
        )
        second_mention = CompoundMention(
            smiles="CC(=O)O",
            extracted_name="Acetic Acid",
        )

        sample_page.update_compound_mentions([first_mention])
        sample_page.update_compound_mentions([second_mention])

        # Domain model replaces mentions, not accumulates them
        assert len(sample_page.compound_mentions) == 1
        assert sample_page.compound_mentions[0].extracted_name == "Acetic Acid"

    def test_compound_mentions_event_generated(
        self,
        sample_page: Page,
        sample_compound_mention: CompoundMention,
    ) -> None:
        """Test that CompoundMentionsUpdated event is created."""
        sample_page.update_compound_mentions([sample_compound_mention])
        events = list(sample_page.collect_events())
        assert len(events) == 2  # Created and CompoundMentionsUpdated
        assert events[1].__class__.__name__ == "CompoundMentionsUpdated"

    def test_compound_mentions_raises_on_deleted_page(
        self,
        sample_page: Page,
        sample_compound_mention: CompoundMention,
    ) -> None:
        """Test that updating compound mentions on deleted page raises error."""
        sample_page.delete()
        with pytest.raises(ValueError, match="Cannot update compound mentions on a deleted page"):
            sample_page.update_compound_mentions([sample_compound_mention])


class TestPageTagMentions:
    """Test updating tag mentions on page."""

    def test_add_tag_mentions(self, sample_page: Page, sample_tag_mention: TagMention) -> None:
        """Test adding tag mentions to a page."""
        sample_page.update_tag_mentions([sample_tag_mention])
        assert len(sample_page.tag_mentions) == 1
        assert sample_page.tag_mentions[0] == sample_tag_mention

    def test_add_multiple_tag_mentions(self, sample_page: Page) -> None:
        """Test adding multiple tag mentions at once."""
        mentions = [
            TagMention(tag="chemistry", confidence=0.88),
            TagMention(tag="biology", confidence=0.85),
        ]
        sample_page.update_tag_mentions(mentions)
        assert len(sample_page.tag_mentions) == 2
        assert sample_page.tag_mentions[0].tag == "chemistry"
        assert sample_page.tag_mentions[1].tag == "biology"

    def test_add_tag_mentions_multiple_times(self, sample_page: Page) -> None:
        """Test that updating tag mentions replaces previous ones (not accumulates)."""
        first_mention = TagMention(tag="chemistry", confidence=0.88)
        second_mention = TagMention(tag="biology", confidence=0.85)

        sample_page.update_tag_mentions([first_mention])
        sample_page.update_tag_mentions([second_mention])

        # Domain model replaces mentions, not accumulates them
        assert len(sample_page.tag_mentions) == 1
        assert sample_page.tag_mentions[0].tag == "biology"

    def test_tag_mentions_event_generated(
        self,
        sample_page: Page,
        sample_tag_mention: TagMention,
    ) -> None:
        """Test that TagMentionsUpdated event is created."""
        sample_page.update_tag_mentions([sample_tag_mention])
        events = list(sample_page.collect_events())
        assert len(events) == 2  # Created and TagMentionsUpdated
        assert events[1].__class__.__name__ == "TagMentionsUpdated"

    def test_tag_mentions_raises_on_deleted_page(
        self,
        sample_page: Page,
        sample_tag_mention: TagMention,
    ) -> None:
        """Test that updating tag mentions on deleted page raises error."""
        sample_page.delete()
        with pytest.raises(ValueError, match="Cannot update tag mentions on a deleted page"):
            sample_page.update_tag_mentions([sample_tag_mention])


class TestPageTextMention:
    """Test updating text mention on page."""

    def test_update_text_mention(self, sample_page: Page, sample_text_mention: TextMention) -> None:
        """Test updating text mention."""
        sample_page.update_text_mention(sample_text_mention)
        assert sample_page.text_mention == sample_text_mention

    def test_update_text_mention_to_none(
        self,
        sample_page: Page,
        sample_text_mention: TextMention,
    ) -> None:
        """Test updating text mention to None."""
        sample_page.update_text_mention(sample_text_mention)
        sample_page.update_text_mention(None)
        assert sample_page.text_mention is None

    def test_text_mention_event_generated(
        self,
        sample_page: Page,
        sample_text_mention: TextMention,
    ) -> None:
        """Test that TextMentionUpdated event is created."""
        sample_page.update_text_mention(sample_text_mention)
        events = list(sample_page.collect_events())
        assert len(events) == 2  # Created and TextMentionUpdated
        assert events[1].__class__.__name__ == "TextMentionUpdated"

    def test_text_mention_raises_on_deleted_page(
        self,
        sample_page: Page,
        sample_text_mention: TextMention,
    ) -> None:
        """Test that updating text mention on deleted page raises error."""
        sample_page.delete()
        with pytest.raises(ValueError, match="Cannot update text mention on a deleted page"):
            sample_page.update_text_mention(sample_text_mention)


class TestPageSummaryCandidate:
    """Test updating summary candidate on page."""

    def test_update_summary_candidate(
        self,
        sample_page: Page,
        sample_summary_candidate: SummaryCandidate,
    ) -> None:
        """Test updating summary candidate."""
        sample_page.update_summary_candidate(sample_summary_candidate)
        assert sample_page.summary_candidate == sample_summary_candidate

    def test_update_summary_candidate_to_none(
        self,
        sample_page: Page,
        sample_summary_candidate: SummaryCandidate,
    ) -> None:
        """Test updating summary candidate to None."""
        sample_page.update_summary_candidate(sample_summary_candidate)
        sample_page.update_summary_candidate(None)
        assert sample_page.summary_candidate is None

    def test_summary_candidate_event_generated(
        self,
        sample_page: Page,
        sample_summary_candidate: SummaryCandidate,
    ) -> None:
        """Test that SummaryCandidateUpdated event is created."""
        sample_page.update_summary_candidate(sample_summary_candidate)
        events = list(sample_page.collect_events())
        assert len(events) == 2  # Created and SummaryCandidateUpdated
        assert events[1].__class__.__name__ == "SummaryCandidateUpdated"

    def test_summary_candidate_raises_on_deleted_page(
        self,
        sample_page: Page,
        sample_summary_candidate: SummaryCandidate,
    ) -> None:
        """Test that updating summary candidate on deleted page raises error."""
        sample_page.delete()
        with pytest.raises(ValueError, match="Cannot update summary candidate on a deleted page"):
            sample_page.update_summary_candidate(sample_summary_candidate)


class TestPageDeletion:
    """Test page deletion."""

    def test_delete_page(self, sample_page: Page) -> None:
        """Test deleting a page."""
        sample_page.delete()
        assert sample_page.is_deleted is True
        assert sample_page.deleted_at is not None

    def test_delete_page_generates_event(self, sample_page: Page) -> None:
        """Test that deleting generates a Deleted event."""
        sample_page.delete()
        events = list(sample_page.collect_events())
        assert events[-1].__class__.__name__ == "Deleted"

    def test_deleted_page_rejects_updates(self, sample_page: Page) -> None:
        """Test that a deleted page rejects updates."""
        sample_page.delete()

        with pytest.raises(ValueError, match="Cannot update"):
            sample_page.update_compound_mentions(
                [CompoundMention(smiles="C", extracted_name="test")],
            )


class TestPageHashing:
    """Test page hashing."""

    def test_page_hash_based_on_id(self, sample_page: Page) -> None:
        """Test that page hash is based on its ID."""
        assert hash(sample_page) == hash(sample_page.id)

    def test_different_pages_different_hash(self, sample_artifact_id: int) -> None:
        """Test that different pages have different hashes."""
        page1 = Page.create(name="Page 1", artifact_id=sample_artifact_id)
        page2 = Page.create(name="Page 2", artifact_id=sample_artifact_id)
        assert hash(page1) != hash(page2)


class TestPageEventSourcing:
    """Test event sourcing reconstitution and replay capabilities for Page aggregate."""

    def test_compound_mentions_updated_event_contains_complete_data(
        self,
        sample_page: Page,
    ) -> None:
        """Test that CompoundMentionsUpdated event captures all necessary data."""
        mentions = [
            CompoundMention(smiles="C1=CC=CC=C1", extracted_name="Benzene", confidence=0.92),
            CompoundMention(smiles="CC(=O)O", extracted_name="Acetic Acid", confidence=0.88),
        ]
        sample_page.update_compound_mentions(mentions)

        events = list(sample_page.collect_events())
        compound_event = events[1]  # Second event after Created

        assert compound_event.__class__.__name__ == "CompoundMentionsUpdated"
        assert compound_event.compound_mentions == mentions
        assert len(compound_event.compound_mentions) == 2
        assert compound_event.compound_mentions[0].smiles == "C1=CC=CC=C1"
        assert compound_event.compound_mentions[0].extracted_name == "Benzene"

    def test_tag_mentions_updated_event_contains_complete_data(self, sample_page: Page) -> None:
        """Test that TagMentionsUpdated event captures all necessary data."""
        mentions = [
            TagMention(tag="chemistry", confidence=0.88),
            TagMention(tag="biology", confidence=0.85),
        ]
        sample_page.update_tag_mentions(mentions)

        events = list(sample_page.collect_events())
        tag_event = events[1]

        assert tag_event.__class__.__name__ == "TagMentionsUpdated"
        assert tag_event.tag_mentions == mentions
        assert len(tag_event.tag_mentions) == 2

    def test_text_mention_updated_event_contains_complete_data(self, sample_page: Page) -> None:
        """Test that TextMentionUpdated event captures all necessary data."""
        text_mention = TextMention(text="Critical result", confidence=0.93)
        sample_page.update_text_mention(text_mention)

        events = list(sample_page.collect_events())
        text_event = events[1]

        assert text_event.__class__.__name__ == "TextMentionUpdated"
        assert text_event.text_mention == text_mention
        assert text_event.text_mention.text == "Critical result"
        assert text_event.text_mention.confidence == 0.93

    def test_summary_candidate_updated_event_contains_complete_data(
        self,
        sample_page: Page,
    ) -> None:
        """Test that SummaryCandidateUpdated event captures all necessary data."""
        summary = SummaryCandidate(summary="Page summary here", confidence=0.87)
        sample_page.update_summary_candidate(summary)

        events = list(sample_page.collect_events())
        summary_event = events[1]

        assert summary_event.__class__.__name__ == "SummaryCandidateUpdated"
        assert summary_event.summary_candidate == summary
        assert summary_event.summary_candidate.summary == "Page summary here"


class TestPageInvariants:
    """Test that domain invariants are properly enforced for Page aggregate."""

    def test_cannot_modify_deleted_page_at_all(self, sample_artifact_id: int) -> None:
        """Test that ALL modifications are rejected on a deleted page."""
        page = Page.create(name="Test", artifact_id=sample_artifact_id)
        page.delete()

        # Every modification should fail
        with pytest.raises(ValueError, match="deleted"):
            page.update_compound_mentions([CompoundMention(smiles="C", extracted_name="Test")])

        with pytest.raises(ValueError, match="deleted"):
            page.update_tag_mentions([TagMention(tag="test", confidence=0.9)])

        with pytest.raises(ValueError, match="deleted"):
            page.update_text_mention(TextMention(text="test", confidence=0.9))

        with pytest.raises(ValueError, match="deleted"):
            page.update_summary_candidate(SummaryCandidate(summary="test", confidence=0.9))

    def test_deletion_is_idempotent(self, sample_artifact_id: int) -> None:
        """Test that deleting an already deleted page doesn't cause issues."""
        page = Page.create(name="Test", artifact_id=sample_artifact_id)

        page.delete()
        first_deleted_at = page.deleted_at

        # Second delete should not raise an error
        page.delete()

        # State should be consistent
        assert page.is_deleted is True

    def test_mentions_replace_not_accumulate(self, sample_artifact_id: int) -> None:
        """Test that updating mentions replaces previous values, doesn't accumulate.

        This is an important design decision that should be explicitly tested.
        """
        page = Page.create(name="Test", artifact_id=sample_artifact_id)

        # First update
        first_compounds = [CompoundMention(smiles="C1", extracted_name="First")]
        page.update_compound_mentions(first_compounds)

        # Second update should replace, not add
        second_compounds = [CompoundMention(smiles="C2", extracted_name="Second")]
        page.update_compound_mentions(second_compounds)

        assert len(page.compound_mentions) == 1
        assert page.compound_mentions[0].extracted_name == "Second"

        # Same for tag mentions
        page.update_tag_mentions([TagMention(tag="first", confidence=0.9)])
        page.update_tag_mentions([TagMention(tag="second", confidence=0.8)])

        assert len(page.tag_mentions) == 1
        assert page.tag_mentions[0].tag == "second"

    def test_empty_mentions_list_is_valid(self, sample_artifact_id: int) -> None:
        """Test that setting empty lists is a valid operation."""
        page = Page.create(name="Test", artifact_id=sample_artifact_id)

        # Add some mentions
        page.update_compound_mentions([CompoundMention(smiles="C", extracted_name="Test")])
        page.update_tag_mentions([TagMention(tag="test", confidence=0.9)])

        # Clear them with empty lists
        page.update_compound_mentions([])
        page.update_tag_mentions([])

        assert page.compound_mentions == []
        assert page.tag_mentions == []

    def test_none_values_clear_optional_fields(self, sample_artifact_id: int) -> None:
        """Test that None explicitly clears optional fields."""
        page = Page.create(name="Test", artifact_id=sample_artifact_id)

        # Set values
        page.update_text_mention(TextMention(text="test", confidence=0.9))
        page.update_summary_candidate(SummaryCandidate(summary="test", confidence=0.9))

        # Clear with None
        page.update_text_mention(None)
        page.update_summary_candidate(None)

        assert page.text_mention is None
        assert page.summary_candidate is None

    def test_version_increments_with_each_event(self, sample_artifact_id: int) -> None:
        """Test that page version properly increments with each state change."""
        page = Page.create(name="Test", artifact_id=sample_artifact_id)

        initial_version = page.version

        page.update_compound_mentions([CompoundMention(smiles="C", extracted_name="Test")])
        assert page.version == initial_version + 1

        page.update_tag_mentions([TagMention(tag="test", confidence=0.9)])
        assert page.version == initial_version + 2

        page.delete()
        assert page.version == initial_version + 3
