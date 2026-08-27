"""Infrastructure implementation of CserService using structflo-cser."""

from __future__ import annotations

import threading
from io import BytesIO
from typing import TYPE_CHECKING

import structlog
from structflo.cser.pipeline import render_page

from application.dtos.cser_dtos import CserCompoundResult
from application.ports.cser_service import CserService

if TYPE_CHECKING:
    from PIL import Image

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

    def _persist_render(self, image: Image.Image, render_key: str) -> None:
        """Write the render the model saw, so stored boxes always have their image."""
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        self._blob_store.put_stream(render_key, buffer, mime_type="image/png")

    def extract_compounds_from_pdf_page(
        self,
        storage_key: str,
        page_index: int,
        render_key: str,
    ) -> list[CserCompoundResult]:
        """Run structflo-cser on one page, keeping the render its boxes refer to."""
        self._ensure_pipeline_loaded()
        logger.info(
            "cser_extracting_compounds",
            storage_key=storage_key,
            page_index=page_index,
        )
        with self._blob_store.get_file(storage_key) as pdf_path:
            result = self._pipeline.process_pdf_page(pdf_path, page_index)

        self._persist_render(result.image, render_key)

        logger.info(
            "cser_extraction_complete",
            storage_key=storage_key,
            page_index=page_index,
            num_pairs=len(result.pairs),
            render_key=render_key,
            render_size=[result.width, result.height],
        )
        # ponytail: a structure whose SMILES no OCSR can read is dropped
        # downstream (CompoundMention.smiles is required and non-blank). Those
        # are exactly the hard detector examples; upgrade path is a separate
        # annotation store, not a relaxed VO.
        return [
            CserCompoundResult(
                smiles=pair.smiles,
                label_text=pair.label_text,
                match_confidence=pair.match_confidence,
                structure_bbox=[int(v) for v in pair.structure.bbox.as_list()],
                label_bbox=[int(v) for v in pair.label.bbox.as_list()],
                structure_confidence=pair.structure.conf,
                label_confidence=pair.label.conf,
            )
            for pair in result.pairs
        ]

    def render_page_only(
        self,
        storage_key: str,
        page_index: int,
        render_key: str,
    ) -> None:
        """Persist the render without inference — no weights are loaded."""
        with self._blob_store.get_file(storage_key) as pdf_path:
            image = render_page(pdf_path, page_index)
        self._persist_render(image, render_key)
        logger.info("cser_render_persisted", render_key=render_key, page_index=page_index)
