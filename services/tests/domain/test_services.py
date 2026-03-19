"""Tests for domain services."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.services.artifact_deletion_service import ArtifactDeletionService
from domain.services.bioactivity_reducer import associate_bioactivities
from domain.services.tag_mention_aggregator import aggregate_tag_mentions
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.tag_mention import TagMention


def _tm(tag: str, entity_type: str, params: dict | None = None) -> TagMention:
    """Helper to build a TagMention for tests."""
    return TagMention(
        tag=tag,
        entity_type=entity_type,
        confidence=0.9,
        date_extracted=datetime.now(UTC),
        model_name="test",
        additional_model_params=params or {"entity_type": entity_type},
    )


def _page_data(tags: list[TagMention], index: int = 0):
    """Helper: wrap a tag list as (page_id, page_index, tags) for aggregate_tag_mentions."""
    return (uuid4(), index, tags)


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


class TestBioactivityReducer:
    """Test associate_bioactivities domain service."""

    def test_basic_association(self) -> None:
        """Bioactivity with matching compound is folded into compound's params."""
        tags = [
            _tm("LG-0019310", "compound_name"),
            _tm("hERG IC50>30µM", "bioactivity", {
                "entity_type": "bioactivity",
                "compound_name": "LG-0019310",
                "assay_type": "IC50",
                "value": ">30",
                "unit": "µM",
            }),
        ]
        result = associate_bioactivities(tags)

        assert len(result) == 1
        assert result[0].tag == "LG-0019310"
        activities = result[0].additional_model_params["bioactivities"]
        assert len(activities) == 1
        assert activities[0]["assay_type"] == "IC50"
        assert activities[0]["value"] == ">30"
        assert activities[0]["unit"] == "µM"
        assert activities[0]["raw_text"] == "hERG IC50>30µM"

    def test_multiple_bioactivities_same_compound(self) -> None:
        """Multiple bioactivities for one compound all get collected."""
        tags = [
            _tm("Aspirin", "compound_name"),
            _tm("IC50 = 5nM", "bioactivity", {
                "entity_type": "bioactivity",
                "compound_name": "Aspirin",
                "assay_type": "IC50",
                "value": "5",
                "unit": "nM",
            }),
            _tm("MIC 2µg/mL", "bioactivity", {
                "entity_type": "bioactivity",
                "compound_name": "Aspirin",
                "assay_type": "MIC",
                "value": "2",
                "unit": "µg/mL",
            }),
        ]
        result = associate_bioactivities(tags)

        assert len(result) == 1
        activities = result[0].additional_model_params["bioactivities"]
        assert len(activities) == 2
        assay_types = {a["assay_type"] for a in activities}
        assert assay_types == {"IC50", "MIC"}

    def test_bioactivity_no_compound_name_discarded(self) -> None:
        """Bioactivity without compound_name is dropped."""
        tags = [
            _tm("Aspirin", "compound_name"),
            _tm("IC50 = 5nM", "bioactivity", {
                "entity_type": "bioactivity",
                "assay_type": "IC50",
                "value": "5",
                "unit": "nM",
            }),
        ]
        result = associate_bioactivities(tags)

        assert len(result) == 1
        assert result[0].tag == "Aspirin"
        assert "bioactivities" not in (result[0].additional_model_params or {})

    def test_bioactivity_unmatched_compound_discarded(self) -> None:
        """Bioactivity referencing a compound not in the tag list is dropped."""
        tags = [
            _tm("Aspirin", "compound_name"),
            _tm("IC50 = 5nM", "bioactivity", {
                "entity_type": "bioactivity",
                "compound_name": "Ibuprofen",
                "assay_type": "IC50",
                "value": "5",
                "unit": "nM",
            }),
        ]
        result = associate_bioactivities(tags)

        assert len(result) == 1
        assert result[0].tag == "Aspirin"
        assert "bioactivities" not in (result[0].additional_model_params or {})

    def test_case_insensitive_matching(self) -> None:
        """Compound name matching is case-insensitive and ignores spaces."""
        tags = [
            _tm("LG-0019310", "compound_name"),
            _tm("IC50>30µM", "bioactivity", {
                "entity_type": "bioactivity",
                "compound_name": "lg-0019310",
                "assay_type": "IC50",
                "value": ">30",
                "unit": "µM",
            }),
        ]
        result = associate_bioactivities(tags)

        assert len(result) == 1
        activities = result[0].additional_model_params["bioactivities"]
        assert len(activities) == 1

    def test_non_bioactivity_tags_preserved(self) -> None:
        """Target, disease, and other entity types pass through unchanged."""
        tags = [
            _tm("Aspirin", "compound_name"),
            _tm("EGFR", "target"),
            _tm("Cancer", "disease"),
        ]
        result = associate_bioactivities(tags)

        assert len(result) == 3
        entity_types = {tm.entity_type for tm in result}
        assert entity_types == {"compound_name", "target", "disease"}

    def test_empty_input(self) -> None:
        """Empty list returns empty list."""
        assert associate_bioactivities([]) == []

    def test_no_bioactivities_returns_original(self) -> None:
        """When there are no bioactivity tags, input is returned as-is."""
        tags = [
            _tm("Aspirin", "compound_name"),
            _tm("EGFR", "target"),
        ]
        result = associate_bioactivities(tags)
        assert result == tags  # equal content, but a safe copy


class TestTagMentionAggregator:
    """Test aggregate_tag_mentions domain service."""

    def test_dedup_same_tag_across_pages(self) -> None:
        """Same target on two pages → one entry, best confidence."""
        page1_tags = [_tm("EGFR", "target", {"entity_type": "target"})]
        page2_tags = [
            TagMention(
                tag="EGFR", entity_type="target", confidence=0.99,
                date_extracted=datetime.now(UTC), model_name="test",
                additional_model_params={"entity_type": "target"},
            ),
        ]
        result = aggregate_tag_mentions([
            _page_data(page1_tags, 0),
            _page_data(page2_tags, 1),
        ])

        assert len(result) == 1
        assert result[0].tag == "EGFR"
        assert result[0].confidence == 0.99

    def test_provenance_populated(self) -> None:
        """Aggregated tags carry provenance with source page info."""
        pid1, pid2 = uuid4(), uuid4()
        page1_tags = [_tm("EGFR", "target")]
        page2_tags = [
            TagMention(
                tag="EGFR", entity_type="target", confidence=0.99,
                date_extracted=datetime.now(UTC), model_name="test",
            ),
        ]
        result = aggregate_tag_mentions([
            (pid1, 0, page1_tags),
            (pid2, 2, page2_tags),
        ])

        assert len(result) == 1
        tag = result[0]
        assert tag.tag_normalized == "egfr"
        assert tag.page_count == 2
        assert tag.max_confidence == 0.99
        assert tag.sources is not None
        assert len(tag.sources) == 2
        source_page_ids = {s.page_id for s in tag.sources}
        assert source_page_ids == {pid1, pid2}

    def test_compound_bioactivities_merged_across_pages(self) -> None:
        """Same compound on two pages with different bioactivities → merged."""
        page1_tags = [_tm("Aspirin", "compound_name", {
            "entity_type": "compound_name",
            "bioactivities": [{"assay_type": "IC50", "value": "5", "unit": "nM", "raw_text": "IC50 5nM"}],
        })]
        page2_tags = [_tm("Aspirin", "compound_name", {
            "entity_type": "compound_name",
            "bioactivities": [{"assay_type": "MIC", "value": "2", "unit": "µg/mL", "raw_text": "MIC 2µg/mL"}],
        })]
        result = aggregate_tag_mentions([
            _page_data(page1_tags, 0),
            _page_data(page2_tags, 1),
        ])

        assert len(result) == 1
        activities = result[0].additional_model_params["bioactivities"]
        assert len(activities) == 2
        assay_types = {a["assay_type"] for a in activities}
        assert assay_types == {"IC50", "MIC"}

    def test_duplicate_bioactivities_deduped(self) -> None:
        """Same bioactivity on two pages → kept once."""
        bio = {"assay_type": "IC50", "value": "5", "unit": "nM", "raw_text": "IC50 5nM"}
        page1_tags = [_tm("Aspirin", "compound_name", {
            "entity_type": "compound_name",
            "bioactivities": [bio],
        })]
        page2_tags = [_tm("Aspirin", "compound_name", {
            "entity_type": "compound_name",
            "bioactivities": [bio],
        })]
        result = aggregate_tag_mentions([
            _page_data(page1_tags, 0),
            _page_data(page2_tags, 1),
        ])

        activities = result[0].additional_model_params["bioactivities"]
        assert len(activities) == 1

    def test_case_insensitive_dedup(self) -> None:
        """Same tag with different casing → one entry."""
        page1_tags = [_tm("EGFR", "target")]
        page2_tags = [_tm("egfr", "target")]
        result = aggregate_tag_mentions([
            _page_data(page1_tags, 0),
            _page_data(page2_tags, 1),
        ])

        assert len(result) == 1

    def test_different_entity_types_not_deduped(self) -> None:
        """Same tag text but different entity types → separate entries."""
        page_tags = [_tm("G2", "gene_name"), _tm("G2", "target")]
        result = aggregate_tag_mentions([_page_data(page_tags, 0)])

        assert len(result) == 2

    def test_empty_pages(self) -> None:
        """Empty input returns empty."""
        assert aggregate_tag_mentions([]) == []
        assert aggregate_tag_mentions([
            _page_data([], 0),
            _page_data([], 1),
        ]) == []

    def test_synonyms_merged(self) -> None:
        """Synonyms from multiple pages are merged."""
        page1_tags = [_tm("Aspirin", "compound_name", {
            "entity_type": "compound_name", "synonyms": "ASA",
        })]
        page2_tags = [_tm("Aspirin", "compound_name", {
            "entity_type": "compound_name", "synonyms": "acetylsalicylic acid",
        })]
        result = aggregate_tag_mentions([
            _page_data(page1_tags, 0),
            _page_data(page2_tags, 1),
        ])

        synonyms = result[0].additional_model_params["synonyms"]
        assert "ASA" in synonyms
        assert "acetylsalicylic acid" in synonyms
