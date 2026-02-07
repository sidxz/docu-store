"""Event projectors for page aggregate read models."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.aggregates.page import Page
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
                "artifact_id": str(event.artifact_id),
                "index": event.index,
                "compound_mentions": [],
                "tag_mentions": [],
                "text_mention": None,
                "summary_candidate": None,
                "workflow_statuses": {},
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def compound_mentions_updated(self, event: object, tracking: object) -> None:
        """Project CompoundMentionsUpdated event to read model."""
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

    def tag_mentions_updated(self, event: object, tracking: object) -> None:
        """Project TagMentionsUpdated event to read model."""
        # Convert Pydantic models to dicts for storage
        tag_mentions_data = [
            tag_mention.model_dump(mode="json")
            for tag_mention in event.tag_mentions  # type: ignore[attr-defined]
        ]
        self._materializer.upsert_page(
            page_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                "tag_mentions": tag_mentions_data,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def text_mention_updated(self, event: object, tracking: object) -> None:
        """Project TextMentionUpdated event to read model."""
        # Convert Pydantic model to dict if not None
        text_mention_data = (
            event.text_mention.model_dump(mode="json") if event.text_mention else None  # type: ignore[attr-defined]
        )
        self._materializer.upsert_page(
            page_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                "text_mention": text_mention_data,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def summary_candidate_updated(self, event: object, tracking: object) -> None:
        """Project SummaryCandidateUpdated event to read model."""
        # Convert Pydantic model to dict if not None
        summary_candidate_data = (
            event.summary_candidate.model_dump(mode="json") if event.summary_candidate else None  # type: ignore[attr-defined]
        )
        self._materializer.upsert_page(
            page_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                "summary_candidate": summary_candidate_data,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def workflow_status_updated(self, event: object, tracking: object) -> None:
        """Project WorkflowStatusUpdated event to read model."""
        status_data = event.status.model_dump(mode="json")  # type: ignore[attr-defined]
        workflow_key = f"workflow_statuses.{event.name}"  # type: ignore[attr-defined]
        self._materializer.upsert_page(
            page_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                workflow_key: status_data,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def page_deleted(self, event: object, tracking: object) -> None:
        """Project PageDeleted event to read model."""
        self._materializer.delete_page(
            page_id=str(event.originator_id),  # type: ignore[attr-defined]
            tracking=tracking,  # type: ignore[arg-type]
        )
