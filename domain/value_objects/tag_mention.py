from pydantic import field_validator

from domain.value_objects.extraction_metadata import ExtractionMetadata


class TagMention(ExtractionMetadata):
    """Represents tag extracted from a page using NLP.

    This value object captures the extracted tag content and metadata
    about the extraction process, including confidence scores and model details.

    """

    tag: str
    """Extracted tag content (required, cannot be blank)."""

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
