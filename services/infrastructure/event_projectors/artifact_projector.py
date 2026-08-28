"""Event projectors for artifact aggregate read models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.services.compound_alias_resolver import is_publishable_alias, synonyms_of

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
                "workspace_id": str(event.workspace_id) if event.workspace_id else None,
                "owner_id": str(event.owner_id) if event.owner_id else None,
                "pages": [],
                "title_mention": None,
                "tag_mentions": [],
                "author_mentions": [],
                "presentation_date": None,
                "summary_candidate": None,
            },
            tracking=tracking,  # type: ignore[arg-type]
        )

    def pages_added(self, event: object, tracking: object) -> None:
        """Project PagesAdded event to read model."""
        page_ids_data = [str(page_id) for page_id in event.page_ids]  # type: ignore[attr-defined]
        self._materializer.add_to_artifact_array(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            field="pages",
            values=page_ids_data,
            tracking=tracking,  # type: ignore[arg-type]
        )

    def pages_removed(self, event: object, tracking: object) -> None:
        """Project PagesRemoved event to read model."""
        page_ids_data = [str(page_id) for page_id in event.page_ids]  # type: ignore[attr-defined]
        self._materializer.pull_from_artifact_array(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            field="pages",
            values=page_ids_data,
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

    def tag_mentions_updated(self, event: object, tracking: object) -> None:
        """Project TagMentionsUpdated event to read model and tag dictionary.

        Uses a combined transaction to avoid duplicate-tracking IntegrityError
        that previously caused the tag_dictionary write to be silently skipped.
        """
        tag_mentions_data = [
            tag_mention.model_dump(mode="json")
            for tag_mention in event.tag_mentions  # type: ignore[attr-defined]
        ]
        tags = [
            {"tag": tm.tag, "tag_normalized": tm.tag.lower(), "entity_type": tm.entity_type}
            for tm in event.tag_mentions  # type: ignore[attr-defined]
        ]
        # An alias merged into its canonical compound must stay findable by its own
        # name, so publish a dictionary row for it too. Numeric-only aliases are
        # document-local ("compound 1") and would be noise workspace-wide.
        tags += [
            {"tag": alias, "tag_normalized": alias.lower(), "entity_type": "compound_name"}
            for tm in event.tag_mentions  # type: ignore[attr-defined]
            if tm.entity_type == "compound_name"
            for alias in synonyms_of(tm)
            if is_publishable_alias(alias)
        ]
        self._materializer.upsert_artifact_and_replace_tags(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={"tag_mentions": tag_mentions_data},
            tags=tags,
            tracking=tracking,  # type: ignore[arg-type]
        )

    def author_mentions_updated(self, event: object, tracking: object) -> None:
        """Project AuthorMentionsUpdated event to read model and tag dictionary."""
        author_mentions_data = [
            author_mention.model_dump(mode="json")
            for author_mention in event.author_mentions  # type: ignore[attr-defined]
        ]
        tags = [
            {"tag": am.name, "tag_normalized": am.name.lower(), "entity_type": "author"}
            for am in event.author_mentions  # type: ignore[attr-defined]
        ]
        self._materializer.upsert_artifact_and_replace_tags(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={"author_mentions": author_mentions_data},
            tags=tags,
            tracking=tracking,  # type: ignore[arg-type]
        )

    def presentation_date_updated(self, event: object, tracking: object) -> None:
        """Project PresentationDateUpdated event to read model and tag dictionary."""
        presentation_date_data = (
            event.presentation_date.model_dump(mode="json") if event.presentation_date else None  # type: ignore[attr-defined]
        )

        # Project date year to tag dictionary
        if event.presentation_date and event.presentation_date.date:  # type: ignore[attr-defined]
            year = event.presentation_date.date.year  # type: ignore[attr-defined]
            tags = [{"tag": str(year), "tag_normalized": str(year), "entity_type": "date"}]
        else:
            tags = []
        self._materializer.upsert_artifact_and_replace_tags(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields={"presentation_date": presentation_date_data},
            tags=tags,
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

    def human_correction_recorded(self, event: object, tracking: object) -> None:
        """Project HumanCorrectionRecorded event to read model (hiledit).

        Uses dotted-path keys (``human_corrections.<field>``) so a Mongo ``$set``
        writes only the corrected field's provenance, leaving corrections already
        recorded for other fields untouched instead of overwriting the whole
        subdocument.
        """
        fields = {
            f"human_corrections.{name}": {
                "corrected_by_id": event.corrected_by_id,  # type: ignore[attr-defined]
                "corrected_by_name": event.corrected_by_name,  # type: ignore[attr-defined]
                "corrected_at": event.corrected_at.isoformat(),  # type: ignore[attr-defined]
            }
            for name in event.corrected_fields  # type: ignore[attr-defined]
        }
        self._materializer.upsert_artifact(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            fields=fields,
            tracking=tracking,  # type: ignore[arg-type]
        )

    def artifact_deleted(self, event: object, tracking: object) -> None:
        """Project ArtifactDeleted event to read model."""
        # Remove from tag dictionary before deleting artifact read model
        self._materializer.replace_artifact_tags(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            tags=[],
            tracking=tracking,  # type: ignore[arg-type]
        )
        self._materializer.delete_artifact(
            artifact_id=str(event.originator_id),  # type: ignore[attr-defined]
            tracking=tracking,  # type: ignore[arg-type]
        )
