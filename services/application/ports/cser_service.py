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
        render_key: str,
    ) -> list[CserCompoundResult]:
        """Render a PDF page, persist that render, and extract compound pairs.

        Args:
            storage_key: Blob store key pointing to the source PDF file.
            page_index: Zero-based page number to process.
            render_key: Blob store key to write the render to. Returned bounding
                boxes are in that image's pixel coordinates.

        Returns:
            List of raw compound results. May be empty if nothing is detected.

        """
        ...

    def render_page_only(
        self,
        storage_key: str,
        page_index: int,
        render_key: str,
    ) -> None:
        """Persist the render for a page WITHOUT running inference.

        For pages whose compound mentions are human-owned: the overlay and the
        training export still need the image, but re-running the model would be
        wasted work and its output would be discarded by the aggregate anyway.
        """
        ...

    def analyze_boxes(
        self,
        render_key: str,
        structure_bbox: list[float] | None,
        label_bbox: list[float] | None,
    ) -> tuple[str | None, str | None]:
        """Read a human-drawn box pair on a stored render: SMILES + label text.

        Args:
            render_key: Blob key of the CSER render the coordinates refer to.
            structure_bbox: ``[x1, y1, x2, y2]`` to run OCSR on, or None to skip.
            label_bbox: ``[x1, y1, x2, y2]`` to run OCR on, or None to skip.

        Returns:
            ``(smiles, label_text)``; either side is None when its box was not
            supplied or the model could not read the crop. Both None with both
            boxes None is the deliberate warm-up call — it still loads the
            pipeline.

        """
        ...
