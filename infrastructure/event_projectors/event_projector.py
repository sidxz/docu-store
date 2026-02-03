"""Event projection handler with minimal indirection."""

from __future__ import annotations

import structlog

from domain.aggregates.page import Page
from infrastructure.event_projectors.page_projector import PageProjector
from infrastructure.read_repositories.read_model_materializer import ReadModelMaterializer

logger = structlog.get_logger()


class EventProjector:
    """Simple event to projector handler mapping."""

    def __init__(self, materializer: ReadModelMaterializer) -> None:
        self._materializer = materializer
        page_projector = PageProjector(materializer)

        # Map event types directly to handler methods
        self._handlers = {
            Page.Created: page_projector.page_created,
            Page.CompoundMentionsUpdated: page_projector.compound_mentions_updated,
        }

    def process_event(self, event: object, tracking: object) -> None:
        """Route event to appropriate handler."""
        handler = self._handlers.get(type(event))
        if handler is None:
            logger.warning(
                "projector_no_handler_for_event",
                event_type=type(event).__name__,
            )
            return
        handler(event, tracking)

    @property
    def materializer(self) -> ReadModelMaterializer:
        """Get the materializer instance."""
        return self._materializer

    @property
    def topics(self) -> list[type]:
        """Get all event types handled."""
        return list(self._handlers.keys())
