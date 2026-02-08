"""Tests for mappers."""

from __future__ import annotations

from application.mappers.artifact_mappers import ArtifactMapper
from application.mappers.page_mappers import PageMapper


class TestArtifactMapper:
    """Test ArtifactMapper."""

    def test_map_artifact_to_response(self, sample_artifact) -> None:
        """Test mapping Artifact aggregate to response DTO."""
        response = ArtifactMapper.to_artifact_response(sample_artifact)

        assert response.artifact_id == sample_artifact.id
        assert response.source_uri == sample_artifact.source_uri
        assert response.source_filename == sample_artifact.source_filename
        assert response.artifact_type == sample_artifact.artifact_type
        assert response.mime_type == sample_artifact.mime_type
        assert response.storage_location == sample_artifact.storage_location
        assert response.pages == []
        assert response.tags == []
        assert response.title_mention is None
        assert response.summary_candidate is None

    def test_map_artifact_with_pages(self, sample_artifact) -> None:
        """Test mapping artifact with pages."""
        from uuid import uuid4

        page_ids = [uuid4(), uuid4()]
        sample_artifact.add_pages(page_ids)

        response = ArtifactMapper.to_artifact_response(sample_artifact)
        assert response.pages == page_ids

    def test_map_artifact_with_tags(self, sample_artifact) -> None:
        """Test mapping artifact with tags."""
        tags = ["chemistry", "research"]
        sample_artifact.update_tags(tags)

        response = ArtifactMapper.to_artifact_response(sample_artifact)
        assert response.tags == tags

    def test_map_artifact_with_title_mention(self, sample_artifact, sample_title_mention) -> None:
        """Test mapping artifact with title mention."""
        sample_artifact.update_title_mention(sample_title_mention)

        response = ArtifactMapper.to_artifact_response(sample_artifact)
        assert response.title_mention == sample_title_mention

    def test_map_artifact_with_summary_candidate(
        self,
        sample_artifact,
        sample_summary_candidate,
    ) -> None:
        """Test mapping artifact with summary candidate."""
        sample_artifact.update_summary_candidate(sample_summary_candidate)

        response = ArtifactMapper.to_artifact_response(sample_artifact)
        assert response.summary_candidate == sample_summary_candidate


class TestPageMapper:
    """Test PageMapper."""

    def test_map_page_to_response(self, sample_page) -> None:
        """Test mapping Page aggregate to response DTO."""
        response = PageMapper.to_page_response(sample_page)

        assert response.page_id == sample_page.id
        assert response.artifact_id == sample_page.artifact_id
        assert response.name == sample_page.name
        assert response.index == sample_page.index
        assert response.compound_mentions == []
        assert response.tag_mentions == []
        assert response.text_mention is None
        assert response.summary_candidate is None

    def test_map_page_with_compound_mentions(
        self,
        sample_page,
        sample_compound_mention,
    ) -> None:
        """Test mapping page with compound mentions."""
        sample_page.update_compound_mentions([sample_compound_mention])

        response = PageMapper.to_page_response(sample_page)
        assert len(response.compound_mentions) == 1
        assert response.compound_mentions[0].smiles == sample_compound_mention.smiles
        assert (
            response.compound_mentions[0].extracted_name == sample_compound_mention.extracted_name
        )

    def test_map_page_with_tag_mentions(self, sample_page, sample_tag_mention) -> None:
        """Test mapping page with tag mentions."""
        sample_page.update_tag_mentions([sample_tag_mention])

        response = PageMapper.to_page_response(sample_page)
        assert len(response.tag_mentions) == 1
        assert response.tag_mentions[0] == sample_tag_mention

    def test_map_page_with_text_mention(self, sample_page, sample_text_mention) -> None:
        """Test mapping page with text mention."""
        sample_page.update_text_mention(sample_text_mention)

        response = PageMapper.to_page_response(sample_page)
        assert response.text_mention == sample_text_mention

    def test_map_page_with_summary_candidate(
        self,
        sample_page,
        sample_summary_candidate,
    ) -> None:
        """Test mapping page with summary candidate."""
        sample_page.update_summary_candidate(sample_summary_candidate)

        response = PageMapper.to_page_response(sample_page)
        assert response.summary_candidate == sample_summary_candidate
