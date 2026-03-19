"""GLiNER2 adapter implementing StructuredExtractorPort.

Uses the gliner2 library (https://github.com/fastino-ai/GLiNER2) for
schema-driven structured extraction via extract_entities().
Model is lazy-loaded on first call and thread-safe (read-only after init).
"""

from __future__ import annotations

import asyncio
import threading

import structlog

from application.ports.structured_extractor import ExtractedField

logger = structlog.get_logger()


class GLiNER2Extractor:
    """Infrastructure adapter for GLiNER2 structured extraction.

    Implements StructuredExtractorPort. Lazy-loads the model on first use.
    """

    def __init__(
        self,
        model_name: str = "fastino/gliner2-large-v1",
    ) -> None:
        self._model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _ensure_model(self) -> None:
        """Lazy-load the GLiNER2 model (thread-safe)."""
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return  # Double-check after acquiring lock
            logger.info(
                "gliner2_extractor.loading_model",
                model_name=self._model_name,
            )
            from gliner2 import GLiNER2  # noqa: PLC0415

            self._model = GLiNER2.from_pretrained(self._model_name)
            logger.info("gliner2_extractor.model_loaded")

    async def extract(
        self,
        text: str,
        schema: list[str],
        *,
        threshold: float = 0.3,
    ) -> list[ExtractedField]:
        """Extract structured fields from text using GLiNER2.

        Args:
            text: Plain text to extract from.
            schema: List of field definitions in "name::type::description" format.
            threshold: Minimum confidence threshold.

        Returns:
            List of ExtractedField with name, value, and score.

        """
        self._ensure_model()

        # Parse schema into entity type labels
        labels = [field_def.split("::")[0] for field_def in schema]

        # Run extraction in thread pool (model inference is CPU-bound)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._model.extract_entities(
                text,
                labels,
                threshold=threshold,
                include_confidence=True,
            ),
        )

        # extract_entities returns: {"entities": {"label": [{"text": ..., "confidence": ...}]}}
        entities_by_label = result.get("entities", {})
        results = [
            ExtractedField(
                name=label,
                value=entity["text"],
                score=entity.get("confidence", 0.0),
            )
            for label, entities in entities_by_label.items()
            for entity in entities
        ]

        logger.info(
            "gliner2_extractor.extracted",
            field_count=len(results),
            labels=labels,
        )
        return results
