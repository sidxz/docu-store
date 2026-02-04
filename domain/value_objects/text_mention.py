from pydantic import field_validator

from domain.value_objects.extraction_metadata import ExtractionMetadata


class TextMention(ExtractionMetadata):
    """Represents text extracted from a page using NLP.

    This value object captures the extracted text content and metadata
    about the extraction process, including confidence scores and model details.

    """

    text: str
    """Extracted text content (required, cannot be blank)."""

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Validate that text is not blank or empty."""
        if not v or not v.strip():
            msg = "Text cannot be blank or empty"
            raise ValueError(msg)
        return v

    # Define a comparison method for easier testing and comparisons
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TextMention):
            return NotImplemented
        return self.text == other.text

    def __hash__(self) -> int:
        return hash(self.text)
