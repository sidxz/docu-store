"""Tests for domain services."""

from __future__ import annotations

from datetime import UTC, datetime

from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.services.artifact_deletion_service import ArtifactDeletionService
from domain.services.bioactivity_reducer import associate_bioactivities
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
        assert result is tags  # same object, no copy
