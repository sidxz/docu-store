from pydantic import field_validator

from domain.value_objects.extraction_metadata import ExtractionMetadata


class TitleMention(ExtractionMetadata):
    """Represents title extracted from a page using NLP.

    This value object captures the extracted title content and metadata
    about the extraction process, including confidence scores and model details.

    """

    title: str
    """Extracted title content (required, cannot be blank)."""

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate that title is not blank or empty."""
        if not v or not v.strip():
            msg = "Title cannot be blank or empty"
            raise ValueError(msg)
        return v

    # Define a comparison method for easier testing and comparisons
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TitleMention):
            return NotImplemented
        return self.title == other.title

    def __hash__(self) -> int:
        return hash(self.title)
