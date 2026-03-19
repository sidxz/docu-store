"""Port for extracting document titles from PDF layout/font analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class TitleCandidate:
    """A title extracted from PDF font/layout analysis."""

    title: str
    confidence: float
    method: str = "font_analysis"


class TitleExtractorPort(Protocol):
    """Abstract port for extracting document titles from PDF files.

    Implementations use layout-based heuristics (e.g., font size analysis)
    rather than NLP models, making them fast and deterministic.
    """

    def extract_title(self, pdf_path: Path, page_index: int = 0) -> TitleCandidate | None:
        """Extract a title candidate from a specific page of a PDF.

        Args:
            pdf_path: Path to the PDF file on disk.
            page_index: Zero-based page index to analyze.

        Returns:
            TitleCandidate if a title was found, None otherwise.

        """
        ...
