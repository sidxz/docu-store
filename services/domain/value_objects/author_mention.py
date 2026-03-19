from pydantic import field_validator

from domain.value_objects.extraction_metadata import ExtractionMetadata


class AuthorMention(ExtractionMetadata):
    """Represents an author extracted from a document.

    This value object captures the extracted author name and metadata
    about the extraction process.
    """

    name: str
    """Extracted author name (required, cannot be blank)."""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate that name is not blank or empty."""
        if not v or not v.strip():
            msg = "Author name cannot be blank or empty"
            raise ValueError(msg)
        return v

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AuthorMention):
            return NotImplemented
        return self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)
