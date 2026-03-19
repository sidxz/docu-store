import datetime

from pydantic import Field

from domain.value_objects.extraction_metadata import ExtractionMetadata


class PresentationDate(ExtractionMetadata):
    """Represents a date extracted from a document (presentation, publication, etc.).

    This value object captures the parsed date and metadata about the extraction,
    including which extraction method produced it.
    """

    date: datetime.datetime
    """Parsed date value."""

    source: str | None = Field(
        None,
        description="Extraction method that produced this date (e.g. 'gliner2', 'llm').",
    )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PresentationDate):
            return NotImplemented
        return self.date == other.date

    def __hash__(self) -> int:
        return hash(self.date)
