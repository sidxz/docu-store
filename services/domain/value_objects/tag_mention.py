from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from domain.value_objects.extraction_metadata import ExtractionMetadata


class TagSource(BaseModel):
    """Provenance: which page contributed a tag to the artifact-level aggregate."""

    page_id: UUID
    page_index: int = Field(ge=0)
    confidence: float | None = None


class TagMention(ExtractionMetadata):
    """Represents tag extracted from a page using NLP.

    This value object captures the extracted tag content and metadata
    about the extraction process, including confidence scores and model details.

    On artifact-level aggregated tags, the provenance fields (tag_normalized,
    sources, max_confidence, page_count) are populated to track which pages
    contributed each tag.
    """

    tag: str
    """Extracted tag content (required, cannot be blank)."""

    entity_type: str | None = None
    """NER entity type (e.g. 'compound_name', 'target', 'gene_name', 'disease').
    None for generic tags not produced by a typed NER extractor."""

    # Provenance fields — populated on artifact-level aggregated tags, None on page-level
    tag_normalized: str | None = None
    """Lowercase, whitespace-collapsed key for grouping and lookups."""

    sources: list[TagSource] | None = None
    """Pages that contributed this tag to the artifact aggregate."""

    max_confidence: float | None = None
    """Highest confidence across all source pages."""

    page_count: int | None = None
    """Number of distinct pages where this tag was found."""

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, v: str) -> str:
        """Validate that tag is not blank or empty."""
        if not v or not v.strip():
            msg = "Tag cannot be blank or empty"
            raise ValueError(msg)
        return v

    # Define a comparison method for easier testing and comparisons
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TagMention):
            return NotImplemented
        return self.tag == other.tag

    def __hash__(self) -> int:
        return hash(self.tag)
