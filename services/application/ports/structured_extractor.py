"""Port for structured information extraction (e.g. GLiNER2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ExtractedField:
    """A single field extracted from text via structured extraction."""

    name: str
    """Field name from the schema (e.g. 'title', 'author_name')."""

    value: str
    """Extracted text value."""

    score: float
    """Confidence score 0-1."""


class StructuredExtractorPort(Protocol):
    """Abstract port for schema-driven structured extraction.

    Implementations accept a text and a list of schema field definitions,
    returning extracted fields with confidence scores.

    Schema format follows GLiNER2 convention: ["field_name::type::description", ...].
    """

    async def extract(
        self,
        text: str,
        schema: list[str],
        *,
        threshold: float = 0.3,
    ) -> list[ExtractedField]:
        """Extract structured fields from text according to a schema.

        Args:
            text: Plain text to extract from.
            schema: List of field definitions in "name::type::description" format.
            threshold: Minimum confidence threshold for returned fields.

        Returns:
            List of extracted fields with name, value, and confidence score.

        """
        ...
