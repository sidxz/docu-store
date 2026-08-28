"""Infrastructure implementation of CserService using structflo-cser."""

from __future__ import annotations

import threading
import time
from io import BytesIO
from typing import TYPE_CHECKING

import structlog
from PIL import Image
from structflo.cser.pipeline import BBox, CompoundPair, Detection, render_page

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
        self._warmed = False
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

    def analyze_boxes(
        self,
        render_key: str,
        structure_bbox: list[float] | None,
        label_bbox: list[float] | None,
    ) -> tuple[str | None, str | None]:
        """Read one human-drawn box pair on an already-stored render.

        Both boxes None is the warm-up call: it forces the OCSR and OCR models
        to load (~2 min cold, near-instant afterwards) and returns nothing.
        Constructing ChemPipeline alone does NOT do that — DECIMER and the OCR
        reader load their weights on first extract — so the warm-up runs both
        extractors over a throwaway blank image for the side effect.
        """
        self._ensure_pipeline_loaded()
        if structure_bbox is None and label_bbox is None:
            self._warm_extractors()
            return None, None

        with self._blob_store.get_file(render_key) as path:
            image = Image.open(path).convert("RGB")

        # Both sides of CompoundPair are required, so the box that was NOT sent
        # gets a placeholder — never passed to an extractor, only constructed.
        placeholder = [0.0, 0.0, 1.0, 1.0]
        pair = CompoundPair(
            structure=Detection(bbox=BBox(*(structure_bbox or placeholder)), conf=1.0, class_id=0),
            label=Detection(bbox=BBox(*(label_bbox or placeholder)), conf=1.0, class_id=1),
            match_distance=0.0,
        )
        smiles = self._pipeline.extract_smiles(image, pair) if structure_bbox else None
        label_text = self._pipeline.extract_text(image, pair) if label_bbox else None
        logger.info(
            "cser_box_analyzed",
            render_key=render_key,
            has_structure=structure_bbox is not None,
            has_label=label_bbox is not None,
            read_smiles=smiles is not None,
        )
        return smiles, label_text

    def _warm_extractors(self) -> None:
        """Force DECIMER + the OCR reader to load their weights. Best-effort.

        A blank crop makes both extractors return None or raise, which is fine:
        the weights are in memory either way, and a failed warm-up must never
        reach the caller as an error.
        """
        if self._warmed:
            return
        # Measured: 104.6 s cold, but ~8 s on every repeat (DECIMER runs on the
        # blank crop), and the client fires this on each edit-mode open.
        started = time.monotonic()
        image = Image.new("RGB", (64, 64), "white")
        box = Detection(bbox=BBox(0, 0, 64, 64), conf=1.0, class_id=0)
        pair = CompoundPair(structure=box, label=box, match_distance=0.0)
        for extract in (self._pipeline.extract_smiles, self._pipeline.extract_text):
            try:
                extract(image, pair)
            except Exception:  # warm-up is best-effort by design
                logger.debug("cser_warmup_extractor_failed", extractor=extract.__name__)
        self._warmed = True
        logger.info("cser_models_warmed", elapsed_seconds=round(time.monotonic() - started, 1))
