"""Infrastructure implementation of CserService using structflo-cser."""

from __future__ import annotations

import tempfile
import threading
from typing import TYPE_CHECKING

import structlog

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
        self._lock = threading.Lock()

    def _ensure_pipeline_loaded(self) -> None:
        """Lazy-load the ChemPipeline (thread-safe double-check locking)."""
        if self._pipeline is not None:
            return
        with self._lock:
            if self._pipeline is not None:
                return
            from structflo.cser.pipeline import ChemPipeline

            logger.info("cser_pipeline_loading")
            self._pipeline = ChemPipeline()
            logger.info("cser_pipeline_loaded")

    def extract_compounds_from_pdf_page(
        self,
        storage_key: str,
        page_index: int,
    ) -> list[CserCompoundResult]:
        """Hand the page to structflo-cser's own PDF path.

        Rendering (DPI, colour space) follows the library's contract rather than
        a constant kept here: the pipeline is scale-sensitive around its
        operating point. On the PMC9250831 deck our former 2x (144 dpi) render
        lost one of two structure/label pairs that the library's default render
        finds, and 200+ dpi finds none (pages are letterboxed to imgsz=1280).
        The library owns that number; consumers must not guess it.
        """
        import fitz  # PyMuPDF — already a project dependency

        self._ensure_pipeline_loaded()
        logger.info(
            "cser_extracting_compounds",
            storage_key=storage_key,
            page_index=page_index,
        )
        with (
            self._blob_store.get_file(storage_key) as pdf_path,
            tempfile.NamedTemporaryFile(suffix=".pdf") as one_page,
        ):
            source = fitz.open(pdf_path)
            single = fitz.open()
            single.insert_pdf(source, from_page=page_index, to_page=page_index)
            single.save(one_page.name)
            single.close()
            source.close()
            per_page = self._pipeline.process_pdf(one_page.name)
        pairs = per_page[0] if per_page else []
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
