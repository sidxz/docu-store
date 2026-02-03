"""Event projectors for page aggregate read models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.aggregates.page import Page

if TYPE_CHECKING:
    from infrastructure.read_repositories.read_model_materializer import ReadModelMaterializer


class PageProjector:
    """Projects page domain events to MongoDB read models."""

    def __init__(self, materializer: ReadModelMaterializer) -> None:  # type: ignore[name-defined]
        self._materializer = materializer

    def page_created(self, event: Page.Created, tracking: object) -> None:
        """Project Page Created event to read model."""
        self._materializer.upsert_page(
            page_id=str(event.originator_id),
            fields={
                "name": event.name,
                "artifact_id": event.artifact_id,
                "index": event.index,
                "compound_mentions": [],
                "tag_mentions": [],
                "text_mention": None,
                "summary_candidate": None,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def compound_mentions_updated(self, event: object, tracking: object) -> None:
        """Project CompoundMentions Added event to read model."""
        # Convert Pydantic models to dicts for storage
        compound_mentions_data = [
            compound_mention.model_dump(mode="json")
            for compound_mention in event.compound_mentions  # type: ignore[attr-defined]
        ]
        self._materializer.upsert_page(
            page_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                "compound_mentions": compound_mentions_data,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )
