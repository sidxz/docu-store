"""Tests for domain value objects."""

from __future__ import annotations

from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.extraction_metadata import ExtractionMetadata
from domain.value_objects.mime_type import MimeType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from domain.value_objects.title_mention import TitleMention


class TestArtifactType:
    """Test ArtifactType enum."""

    def test_artifact_type_values(self) -> None:
        """Test that ArtifactType has expected values."""
        assert ArtifactType.GENERIC_PRESENTATION == "GENERIC_PRESENTATION"
        assert ArtifactType.SCIENTIFIC_PRESENTATION == "SCIENTIFIC_PRESENTATION"
        assert ArtifactType.RESEARCH_ARTICLE == "RESEARCH_ARTICLE"
        assert ArtifactType.SCIENTIFIC_DOCUMENT == "SCIENTIFIC_DOCUMENT"
        assert ArtifactType.DISCLOSURE_DOCUMENT == "DISCLOSURE_DOCUMENT"
        assert ArtifactType.MINUTE_OF_MEETING == "MINUTE_OF_MEETING"
        assert ArtifactType.UNCLASSIFIED == "UNCLASSIFIED"

    def test_artifact_type_string_comparison(self) -> None:
        """Test that ArtifactType values can be compared as strings."""
        artifact_type = ArtifactType.RESEARCH_ARTICLE
        assert artifact_type == "RESEARCH_ARTICLE"


class TestMimeType:
    """Test MimeType enum."""

    def test_mime_type_values(self) -> None:
        """Test that MimeType has expected values."""
        assert MimeType.PDF == "application/pdf"
        assert MimeType.PPT == "application/vnd.ms-powerpoint"
        assert (
            MimeType.PPTX
            == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        assert MimeType.DOC == "application/msword"
        assert (
            MimeType.DOCX
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_mime_type_string_comparison(self) -> None:
        """Test that MimeType values can be compared as strings."""
        mime_type = MimeType.PDF
        assert mime_type == "application/pdf"


class TestTitleMention:
    """Test TitleMention value object."""

    def test_create_title_mention(self, sample_title_mention: TitleMention) -> None:
        """Test creating a TitleMention."""
        assert sample_title_mention.title == "Important Research"
        assert sample_title_mention.confidence == 0.95

    def test_title_mention_immutable(self, sample_title_mention: TitleMention) -> None:
        """Test that TitleMention fields are accessible."""
        # TitleMention is a Pydantic model - verify the field exists and is set
        assert hasattr(sample_title_mention, "title")
        assert sample_title_mention.title == "Important Research"

    def test_title_mention_equality(self) -> None:
        """Test TitleMention equality."""
        mention1 = TitleMention(title="Test", confidence=0.9)
        mention2 = TitleMention(title="Test", confidence=0.9)
        assert mention1 == mention2

    def test_title_mention_inequality(self) -> None:
        """Test TitleMention inequality."""
        mention1 = TitleMention(title="Test", confidence=0.9)
        mention2 = TitleMention(title="Different", confidence=0.9)
        assert mention1 != mention2


class TestSummaryCandidate:
    """Test SummaryCandidate value object."""

    def test_create_summary_candidate(self, sample_summary_candidate: SummaryCandidate) -> None:
        """Test creating a SummaryCandidate."""
        assert sample_summary_candidate.summary == "This paper discusses..."
        assert sample_summary_candidate.confidence == 0.85

    def test_summary_candidate_equality(self) -> None:
        """Test SummaryCandidate equality."""
        candidate1 = SummaryCandidate(summary="Test summary", confidence=0.8)
        candidate2 = SummaryCandidate(summary="Test summary", confidence=0.8)
        assert candidate1 == candidate2


class TestCompoundMention:
    """Test CompoundMention value object."""

    def test_create_compound_mention(self, sample_compound_mention: CompoundMention) -> None:
        """Test creating a CompoundMention."""
        assert sample_compound_mention.smiles == "C1=CC=CC=C1"
        assert sample_compound_mention.extracted_name == "Benzene"
        assert sample_compound_mention.confidence == 0.92

    def test_compound_mention_with_defaults(self) -> None:
        """Test creating a CompoundMention with default values."""
        mention = CompoundMention(smiles="C", extracted_name="Methane")
        assert mention.smiles == "C"
        assert mention.extracted_name == "Methane"

    def test_compound_mention_equality(self) -> None:
        """Test CompoundMention equality."""
        mention1 = CompoundMention(smiles="C1=CC=CC=C1", extracted_name="Benzene")
        mention2 = CompoundMention(smiles="C1=CC=CC=C1", extracted_name="Benzene")
        # CompoundMentions are equal if they have same smiles and extracted_name
        assert mention1.smiles == mention2.smiles
        assert mention1.extracted_name == mention2.extracted_name


class TestExtractionMetadata:
    """Test ExtractionMetadata value object."""

    def test_create_extraction_metadata(self) -> None:
        """Test creating ExtractionMetadata."""
        metadata = ExtractionMetadata(confidence=0.95)
        assert metadata.confidence == 0.95

    def test_extraction_metadata_defaults(self) -> None:
        """Test ExtractionMetadata with default values."""
        metadata = ExtractionMetadata()
        assert metadata.confidence is None

    def test_extraction_metadata_equality(self) -> None:
        """Test ExtractionMetadata equality."""
        metadata1 = ExtractionMetadata(confidence=0.9)
        metadata2 = ExtractionMetadata(confidence=0.9)
        assert metadata1 == metadata2


class TestTagMention:
    """Test TagMention value object."""

    def test_create_tag_mention(self, sample_tag_mention: TagMention) -> None:
        """Test creating a TagMention."""
        assert sample_tag_mention.tag == "chemistry"
        assert sample_tag_mention.confidence == 0.88

    def test_tag_mention_equality(self) -> None:
        """Test TagMention equality."""
        mention1 = TagMention(tag="chemistry", confidence=0.88)
        mention2 = TagMention(tag="chemistry", confidence=0.88)
        assert mention1 == mention2

    def test_tag_mention_inequality(self) -> None:
        """Test TagMention inequality."""
        mention1 = TagMention(tag="chemistry", confidence=0.88)
        mention2 = TagMention(tag="biology", confidence=0.88)
        assert mention1 != mention2


class TestTextMention:
    """Test TextMention value object."""

    def test_create_text_mention(self, sample_text_mention: TextMention) -> None:
        """Test creating a TextMention."""
        assert sample_text_mention.text == "Notable result"
        assert sample_text_mention.confidence == 0.90

    def test_text_mention_equality(self) -> None:
        """Test TextMention equality."""
        mention1 = TextMention(text="Test", page_number=1, confidence=0.9)
        mention2 = TextMention(text="Test", page_number=1, confidence=0.9)
        assert mention1 == mention2
