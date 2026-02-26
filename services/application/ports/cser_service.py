"""Port for the chemical structure extraction (CSER) service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from application.dtos.cser_dtos import CserCompoundResult


class CserService(Protocol):
    """Abstract port for extracting chemical structure-label pairs from document pages.

    Implementations wrap an ML pipeline (e.g. structflo-cser) that detects
    chemical structures and compound labels in a rendered page image, matches
    them, and returns the extracted SMILES + label text for each pair.
    """

    def extract_compounds_from_pdf_page(
        self,
        storage_key: str,
        page_index: int,
    ) -> list[CserCompoundResult]:
        """Render a PDF page and extract all compound structure-label pairs.

        Args:
            storage_key: Blob store key pointing to the source PDF file.
            page_index: Zero-based page number to process.

        Returns:
            List of raw compound results (smiles, label_text, match_confidence).
            May be empty if no compounds are detected.

        """
        ...
