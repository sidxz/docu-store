"""Font-based title extraction using PyMuPDF layout analysis.

Heuristic: the document title is the text rendered in the largest font
on the first page. This works reliably across presentations, research
articles, disclosure documents, and meeting minutes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

from application.ports.title_extractor import TitleCandidate

logger = structlog.get_logger()

# Minimum font size to consider (filters out footnotes, page numbers)
_MIN_FONT_SIZE = 6.0
_MIN_TITLE_LENGTH = 3  # Minimum characters to consider as a valid title

# Tolerance when grouping spans into the "largest font" cluster (in points)
_SIZE_TOLERANCE = 1.0

# Minimum gap between largest and 2nd-largest font to claim high confidence
_HIGH_CONFIDENCE_GAP = 4.0
_MEDIUM_CONFIDENCE_GAP = 2.0


@dataclass
class _FontSpan:
    """A text span with font metadata, extracted from a PDF page."""

    text: str
    font_size: float
    is_bold: bool


class FontTitleExtractor:
    """Infrastructure adapter: extracts titles from PDFs via font-size heuristic.

    Implements TitleExtractorPort.
    """

    def extract_title(self, pdf_path: Path, page_index: int = 0) -> TitleCandidate | None:
        """Extract title from a PDF page using font-size analysis."""
        try:
            spans = self._extract_font_spans(pdf_path, page_index)
        except Exception:
            logger.exception(
                "font_title_extractor.pdf_read_failed",
                pdf_path=str(pdf_path),
                page_index=page_index,
            )
            return None

        if not spans:
            return None

        return self._find_title(spans)

    @staticmethod
    def _extract_font_spans(pdf_path: Path, page_index: int) -> list[_FontSpan]:
        """Extract text spans with font metadata from a PDF page using PyMuPDF."""
        import fitz  # noqa: PLC0415

        doc = fitz.open(str(pdf_path))
        try:
            if page_index >= len(doc):
                return []

            page = doc[page_index]
            page_dict = page.get_text("dict")

            spans: list[_FontSpan] = []
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:  # text blocks only
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue
                        size = span.get("size", 0.0)
                        if size < _MIN_FONT_SIZE:
                            continue
                        # PyMuPDF flags: bit 4 = bold (value 16)
                        flags = span.get("flags", 0)
                        is_bold = bool(flags & (1 << 4))
                        spans.append(_FontSpan(text=text, font_size=size, is_bold=is_bold))

            return spans
        finally:
            doc.close()

    @staticmethod
    def _find_title(spans: list[_FontSpan]) -> TitleCandidate | None:
        """Determine the title from font-size distribution.

        Algorithm:
        1. Find the maximum font size on the page
        2. Collect all spans at or near that size (within tolerance)
        3. Concatenate in reading order
        4. Compute confidence based on the font-size gap to the next tier
        """
        if not spans:
            return None

        max_size = max(s.font_size for s in spans)

        # Collect spans in the largest-font cluster
        title_spans = [s for s in spans if s.font_size >= max_size - _SIZE_TOLERANCE]
        title_text = " ".join(s.text for s in title_spans)

        # Clean up whitespace
        title_text = " ".join(title_text.split())

        if not title_text or len(title_text) < _MIN_TITLE_LENGTH:
            return None

        # Compute confidence from font-size gap
        distinct_sizes = sorted({round(s.font_size, 1) for s in spans}, reverse=True)
        if len(distinct_sizes) >= 2:  # noqa: PLR2004
            gap = distinct_sizes[0] - distinct_sizes[1]
            if gap >= _HIGH_CONFIDENCE_GAP:
                confidence = 0.95
            elif gap >= _MEDIUM_CONFIDENCE_GAP:
                confidence = 0.85
            else:
                confidence = 0.7
        else:
            # Single font size on the page — low confidence
            confidence = 0.5

        logger.debug(
            "font_title_extractor.found",
            title=title_text[:80],
            font_size=max_size,
            confidence=confidence,
            span_count=len(title_spans),
        )

        return TitleCandidate(
            title=title_text,
            confidence=confidence,
        )
