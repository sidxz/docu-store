"""Infrastructure implementation of CserService using structflo-cser."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from PIL import Image

from application.dtos.cser_dtos import CserCompoundResult
from application.ports.cser_service import CserService

if TYPE_CHECKING:
    from application.ports.blob_store import BlobStore

logger = structlog.get_logger()


class CserPipelineService(CserService):
    """Wraps structflo ChemPipeline to implement the CserService port.

    Lazy-loads the ML pipeline on first use to avoid paying startup cost
    until compound extraction is actually needed.
    """

    def __init__(self, blob_store: BlobStore) -> None:
        self._blob_store = blob_store
        self._pipeline = None

    def _ensure_pipeline_loaded(self) -> None:
        if self._pipeline is None:
            from structflo.cser.pipeline import ChemPipeline  # noqa: PLC0415

            logger.info("cser_pipeline_loading")
            self._pipeline = ChemPipeline()
            logger.info("cser_pipeline_loaded")

    def extract_compounds_from_pdf_page(
        self,
        storage_key: str,
        page_index: int,
    ) -> list[CserCompoundResult]:
        """Render a PDF page to an image and run ChemPipeline on it."""
        import fitz  # noqa: PLC0415  # PyMuPDF — already a project dependency

        self._ensure_pipeline_loaded()

        logger.info(
            "cser_extracting_compounds",
            storage_key=storage_key,
            page_index=page_index,
        )

        with self._blob_store.get_file(storage_key) as pdf_path:
            doc = fitz.open(pdf_path)
            page = doc[page_index]
            # 2x zoom gives ~144 dpi — good balance of quality vs. speed
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()

        pairs = self._pipeline.process(image)

        logger.info(
            "cser_extraction_complete",
            storage_key=storage_key,
            page_index=page_index,
            num_pairs=len(pairs),
        )

        return [
            CserCompoundResult(
                smiles=pair.smiles,
                label_text=pair.label_text,
                match_confidence=pair.match_confidence,
            )
            for pair in pairs
        ]
