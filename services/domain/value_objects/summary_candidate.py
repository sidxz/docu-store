from pydantic import Field

from domain.value_objects.extraction_metadata import ExtractionMetadata


class SummaryCandidate(ExtractionMetadata):
    """Represents a summary candidate extracted from a page using NLP.

    This value object captures the summary content and metadata
    about the extraction process, including confidence scores and model details.

    """

    summary: str | None = Field(
        None,
        description="Generated summary content of the page.",
    )
    is_locked: bool = Field(
        default=False,
        description="Indicates if the summary candidate is locked from further modifications",
    )
    hil_correction: str | None = Field(
        None,
        description="Human-in-the-loop correction to the generated summary, if any.",
    )

    # Define a comparison method for easier testing and comparisons
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SummaryCandidate):
            return NotImplemented
        return (
            self.summary == other.summary
            and self.is_locked == other.is_locked
            and self.hil_correction == other.hil_correction
        )

    def __hash__(self) -> int:
        return hash((self.summary, self.is_locked, self.hil_correction))
