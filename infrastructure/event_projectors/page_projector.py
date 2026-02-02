"""Event projectors for page aggregate read models."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.read_repositories.read_model_materializer import ReadModelMaterializer


class PageProjector:
    """Projects page domain events to MongoDB read models."""

    def __init__(self, materializer: ReadModelMaterializer) -> None:  # type: ignore[name-defined]
        self._materializer = materializer

    def page_created(self, event: object) -> None:
        """Project Page Created event to read model."""
        self._materializer.upsert_page(
            page_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                "name": event.name,  # type: ignore[attr-defined]
                "compounds": [],  # Initialize empty compounds list
            },
            tracking=event.tracking,  # type: ignore[attr-defined]
        )

    def compounds_added(self, event: object) -> None:
        """Project Compounds Added event to read model."""
        # Convert Pydantic models to dicts for storage
        compounds_data = [
            compound.model_dump(mode="json")
            for compound in event.compounds  # type: ignore[attr-defined]
        ]
        self._materializer.upsert_page(
            page_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                "compounds": compounds_data,
            },
            tracking=event.tracking,  # type: ignore[attr-defined]
        )
