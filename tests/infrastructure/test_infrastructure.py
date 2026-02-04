"""Tests for infrastructure components."""

from __future__ import annotations

from infrastructure.serialization.pydantic_transcoder import PydanticTranscoding


class TestPydanticTranscoding:
    """Test PydanticTranscoding for event serialization."""

    def test_pydantic_transcoding_with_value_object(self, sample_title_mention) -> None:
        """Test PydanticTranscoding with a value object."""
        # Create transcoding for TitleMention
        transcoding = PydanticTranscoding(type(sample_title_mention))

        # Encode the value object
        encoded = transcoding.encode(sample_title_mention)
        assert isinstance(encoded, dict)
        assert encoded["title"] == sample_title_mention.title

        # Decode back
        decoded = transcoding.decode(encoded)
        assert decoded.title == sample_title_mention.title
        assert decoded.confidence == sample_title_mention.confidence

    def test_pydantic_transcoding_with_summary_candidate(
        self,
        sample_summary_candidate,
    ) -> None:
        """Test PydanticTranscoding with SummaryCandidate."""
        transcoding = PydanticTranscoding(type(sample_summary_candidate))

        encoded = transcoding.encode(sample_summary_candidate)
        assert isinstance(encoded, dict)
        assert encoded["summary"] == sample_summary_candidate.summary

        decoded = transcoding.decode(encoded)
        assert decoded == sample_summary_candidate


class TestEventProjector:
    """Test event projectors for building read models."""

    def test_artifact_projector_imports(self) -> None:
        """Test that artifact projector can be imported."""
        from infrastructure.event_projectors.artifact_projector import ArtifactProjector

        assert ArtifactProjector is not None

    def test_page_projector_imports(self) -> None:
        """Test that page projector can be imported."""
        from infrastructure.event_projectors.page_projector import PageProjector

        assert PageProjector is not None


class TestEventSourcedRepository:
    """Test event sourced repositories."""

    def test_artifact_repository_exists(self) -> None:
        """Test that artifact repository can be imported."""
        from infrastructure.event_sourced_repositories.artifact_repository import (
            EventSourcedArtifactRepository,
        )

        assert EventSourcedArtifactRepository is not None

    def test_page_repository_exists(self) -> None:
        """Test that page repository can be imported."""
        from infrastructure.event_sourced_repositories.page_repository import (
            EventSourcedPageRepository,
        )

        assert EventSourcedPageRepository is not None


class TestReadModelMaterializer:
    """Test read model materializer."""

    def test_read_model_materializer_exists(self) -> None:
        """Test that read model materializer protocol can be imported."""
        from infrastructure.read_repositories.read_model_materializer import (
            ReadModelMaterializer,
        )

        assert ReadModelMaterializer is not None
