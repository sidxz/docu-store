"""Event projectors for artifact aggregate read models."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.aggregates.artifact import Artifact
    from infrastructure.read_repositories.read_model_materializer import ReadModelMaterializer


class ArtifactProjector:
    """Projects artifact domain events to MongoDB read models."""

    def __init__(self, materializer: ReadModelMaterializer) -> None:  # type: ignore[name-defined]
        self._materializer = materializer

    def artifact_created(self, event: Artifact.Created, tracking: object) -> None:
        """Project Artifact Created event to read model."""
        self._materializer.upsert_artifact(
            artifact_id=str(event.originator_id),
            fields={
                "source_uri": event.source_uri,
                "source_filename": event.source_filename,
                "artifact_type": event.artifact_type,
                "mime_type": event.mime_type,
                "storage_location": event.storage_location,
                "pages": [],
                "title_mention": None,
                "tags": [],
                "summary_candidate": None,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def pages_added(self, event: object, tracking: object) -> None:
        """Project PagesAdded event to read model."""
        # Convert UUIDs to strings for storage
        page_ids_data = [str(page_id) for page_id in event.page_ids]  # type: ignore[attr-defined]
        self._materializer.upsert_artifact(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                "pages": page_ids_data,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def pages_removed(self, event: object, tracking: object) -> None:
        """Project PagesRemoved event to read model."""
        # Convert UUIDs to strings for storage
        page_ids_data = [str(page_id) for page_id in event.page_ids]  # type: ignore[attr-defined]
        self._materializer.upsert_artifact(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                "pages": page_ids_data,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def title_mention_updated(self, event: object, tracking: object) -> None:
        """Project TitleMentionUpdated event to read model."""
        # Convert Pydantic model to dict if not None
        title_mention_data = (
            event.title_mention.model_dump(mode="json") if event.title_mention else None  # type: ignore[attr-defined]
        )
        self._materializer.upsert_artifact(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                "title_mention": title_mention_data,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def tags_updated(self, event: object, tracking: object) -> None:
        """Project TagsUpdated event to read model."""
        self._materializer.upsert_artifact(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                "tags": event.tags,  # type: ignore[attr-defined]
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def summary_candidate_updated(self, event: object, tracking: object) -> None:
        """Project SummaryCandidateUpdated event to read model."""
        # Convert Pydantic model to dict if not None
        summary_candidate_data = (
            event.summary_candidate.model_dump(mode="json") if event.summary_candidate else None  # type: ignore[attr-defined]
        )
        self._materializer.upsert_artifact(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={
                "summary_candidate": summary_candidate_data,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def artifact_deleted(self, event: object, tracking: object) -> None:
        """Project ArtifactDeleted event to read model."""
        self._materializer.delete_artifact(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            tracking=tracking,  # type: ignore[arg-type]
        )
