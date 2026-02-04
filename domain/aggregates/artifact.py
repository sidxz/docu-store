from datetime import UTC, datetime
from uuid import UUID

from eventsourcing.domain import Aggregate, event

from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.title_mention import TitleMention


class Artifact(Aggregate):
    """The Aggregate Root for an Artifact."""

    INITIAL_VERSION = 0

    @classmethod
    def create(
        cls,
        source_uri: str,
        source_filename: str,
        artifact_type: ArtifactType,
        mime_type: MimeType,
        storage_location: str,
    ) -> "Artifact":
        """Create a new Artifact aggregate (Factory Method)."""
        return cls(
            source_uri=source_uri,
            source_filename=source_filename,
            artifact_type=artifact_type,
            mime_type=mime_type,
            storage_location=storage_location,
        )

    class Created(Aggregate.Created):
        """Defines the structure of the Artifact Created event."""

        source_uri: str
        source_filename: str
        artifact_type: ArtifactType
        mime_type: MimeType
        storage_location: str

    @event(Created)  # Links this handler to the Created event class above
    def __init__(
        self,
        source_uri: str,
        source_filename: str,
        artifact_type: ArtifactType,
        mime_type: MimeType,
        storage_location: str,
    ) -> None:
        # Strip whitespace BEFORE validation to catch whitespace-only strings
        source_uri = source_uri.strip()
        source_filename = source_filename.strip()
        storage_location = storage_location.strip()

        if not source_uri:
            msg = "source_uri must be provided"
            raise ValueError(msg)
        if not source_filename:
            msg = "source_filename must be provided"
            raise ValueError(msg)
        if not artifact_type:
            msg = "artifact_type must be provided"
            raise ValueError(msg)
        if not mime_type:
            msg = "mime_type must be provided"
            raise ValueError(msg)
        if not storage_location:
            msg = "storage_location must be provided"
            raise ValueError(msg)

        self.source_uri = source_uri
        self.source_filename = source_filename
        self.artifact_type = artifact_type
        self.mime_type = mime_type
        self.storage_location = storage_location
        self._pages: list[UUID] = []
        self.title_mention: TitleMention | None = None
        self.summary_candidate: SummaryCandidate | None = None
        self.tags: list[str] = []
        self.is_deleted: bool = False

    def __hash__(self) -> int:
        """Return hash of the aggregate based on its ID."""
        return hash(self.id)

    # ============================================================================
    # COMMAND METHOD - Page Management
    # ============================================================================
    @property
    def pages(self) -> tuple[UUID, ...]:
        return tuple(self._pages)

    class PagesAdded(Aggregate.Event):
        page_ids: list[UUID]

    def add_pages(self, page_ids: list[UUID]) -> None:
        """Add associated Page IDs to the Artifact (idempotent, no duplicates)."""
        if self.is_deleted:
            raise ValueError("Cannot add pages to a deleted artifact")
        if not page_ids:
            return  # no-op on empty input

        # Deduplicate while preserving order
        unique_in_order = list(dict.fromkeys(page_ids))

        # Keep only pages not already present
        to_add = [pid for pid in unique_in_order if pid not in self._pages]

        if not to_add:
            return  # no-op if nothing changes

        self.trigger_event(self.PagesAdded, page_ids=to_add)

    @event(PagesAdded)
    def _apply_pages_added(self, page_ids: list[UUID]) -> None:
        # Defensive: still avoid duplicates even if events repeat
        existing = set(self._pages)
        for pid in page_ids:
            if pid not in existing:
                self._pages.append(pid)
                existing.add(pid)

    class PagesRemoved(Aggregate.Event):
        page_ids: list[UUID]

    def remove_pages(self, page_ids: list[UUID]) -> None:
        """Remove associated Page IDs from the Artifact (idempotent)."""
        if self.is_deleted:
            raise ValueError("Cannot remove pages from a deleted artifact")
        if not page_ids:
            return  # no-op on empty input

        # Deduplicate while preserving order
        unique_in_order = list(dict.fromkeys(page_ids))

        # Only attempt to remove those that exist
        existing = set(self._pages)
        to_remove = [pid for pid in unique_in_order if pid in existing]

        if not to_remove:
            return  # no-op if nothing changes

        self.trigger_event(self.PagesRemoved, page_ids=to_remove)

    @event(PagesRemoved)
    def _apply_pages_removed(self, page_ids: list[UUID]) -> None:
        remove_set = set(page_ids)
        if not remove_set:
            return
        self._pages = [pid for pid in self._pages if pid not in remove_set]

    # ============================================================================
    # COMMAND METHOD - Update TitleMention
    # ============================================================================
    class TitleMentionUpdated(Aggregate.Event):
        title_mention: TitleMention | None

    def update_title_mention(self, title_mention: TitleMention | None) -> None:
        if self.is_deleted:
            raise ValueError("Cannot update title mention on a deleted artifact")
        self.trigger_event(self.TitleMentionUpdated, title_mention=title_mention)

    @event(TitleMentionUpdated)
    def _apply_title_mention_updated(self, title_mention: TitleMention | None) -> None:
        self.title_mention = title_mention

    # ============================================================================
    # COMMAND METHOD - update SummaryCandidate
    # ============================================================================
    class SummaryCandidateUpdated(Aggregate.Event):
        summary_candidate: SummaryCandidate | None

    def update_summary_candidate(self, summary_candidate: SummaryCandidate | None) -> None:
        if self.is_deleted:
            raise ValueError("Cannot update summary candidate on a deleted artifact")
        self.trigger_event(self.SummaryCandidateUpdated, summary_candidate=summary_candidate)

    @event(SummaryCandidateUpdated)
    def _apply_summary_candidate_updated(self, summary_candidate: SummaryCandidate | None) -> None:
        self.summary_candidate = summary_candidate

    # ============================================================================
    # COMMAND METHOD - Tag Updated
    # ============================================================================
    class TagsUpdated(Aggregate.Event):
        tags: list[str]

    def update_tags(self, tags: list[str]) -> None:
        if self.is_deleted:
            raise ValueError("Cannot update tags on a deleted artifact")
        # Normalize: strip and drop blanks
        normalized = [t.strip() for t in tags if t and t.strip()]
        # Deduplicate while preserving order
        cleaned_tags = list(dict.fromkeys(normalized))

        if cleaned_tags == self.tags:
            return

        self.trigger_event(self.TagsUpdated, tags=cleaned_tags)

    @event(TagsUpdated)
    def _apply_tags_updated(self, tags: list[str]) -> None:
        self.tags = tags

    # ============================================================================
    # COMMAND METHOD - Delete Artifact
    # ============================================================================
    class Deleted(Aggregate.Event):
        deleted_at: datetime

    def delete(self) -> None:
        """Delete this artifact aggregate."""
        self.trigger_event(self.Deleted, deleted_at=datetime.now(UTC))

    @event(Deleted)
    def _apply_deleted(self, deleted_at: datetime) -> None:
        self.deleted_at = deleted_at
        self.is_deleted = True
