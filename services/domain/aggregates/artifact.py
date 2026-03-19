from datetime import UTC, datetime
from uuid import UUID

from eventsourcing.domain import Aggregate, event

from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.author_mention import AuthorMention
from domain.value_objects.mime_type import MimeType
from domain.value_objects.presentation_date import PresentationDate
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.title_mention import TitleMention


class Artifact(Aggregate):
    """The Aggregate Root for an Artifact."""

    INITIAL_VERSION = 0

    @classmethod
    def create(  # noqa: PLR0913
        cls,
        source_uri: str | None,
        source_filename: str | None,
        artifact_type: ArtifactType,
        mime_type: MimeType,
        storage_location: str,
        artifact_id: UUID | None = None,
        workspace_id: UUID | None = None,
        owner_id: UUID | None = None,
    ) -> "Artifact":
        """Create a new Artifact aggregate (Factory Method)."""
        kwargs = {
            "source_uri": source_uri,
            "source_filename": source_filename,
            "artifact_type": artifact_type,
            "mime_type": mime_type,
            "storage_location": storage_location,
            "workspace_id": workspace_id,
            "owner_id": owner_id,
        }
        if artifact_id is not None:
            kwargs["originator_id"] = artifact_id
        return cls(**kwargs)

    class Created(Aggregate.Created):
        """Defines the structure of the Artifact Created event."""

        source_uri: str | None
        source_filename: str | None
        artifact_type: ArtifactType
        mime_type: MimeType
        storage_location: str
        workspace_id: UUID | None = None
        owner_id: UUID | None = None

    @event(Created)  # Links this handler to the Created event class above
    def __init__(  # noqa: PLR0913
        self,
        source_uri: str | None,
        source_filename: str | None,
        artifact_type: ArtifactType,
        mime_type: MimeType,
        storage_location: str,
        workspace_id: UUID | None = None,
        owner_id: UUID | None = None,
    ) -> None:
        # Strip whitespace BEFORE validation to catch whitespace-only strings
        if source_uri is not None:
            source_uri = source_uri.strip()
        if source_filename is not None:
            source_filename = source_filename.strip()
        storage_location = storage_location.strip()

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
        self.workspace_id = workspace_id
        self.owner_id = owner_id
        self._pages: list[UUID] = []
        self.title_mention: TitleMention | None = None
        self.summary_candidate: SummaryCandidate | None = None
        self.tag_mentions: list[TagMention] = []
        self.author_mentions: list[AuthorMention] = []
        self.presentation_date: PresentationDate | None = None
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
            msg = "Cannot add pages to a deleted artifact"
            raise ValueError(msg)
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
            msg = "Cannot remove pages from a deleted artifact"
            raise ValueError(msg)
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
            msg = "Cannot update title mention on a deleted artifact"
            raise ValueError(msg)
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
            msg = "Cannot update summary candidate on a deleted artifact"
            raise ValueError(msg)
        self.trigger_event(self.SummaryCandidateUpdated, summary_candidate=summary_candidate)

    @event(SummaryCandidateUpdated)
    def _apply_summary_candidate_updated(self, summary_candidate: SummaryCandidate | None) -> None:
        self.summary_candidate = summary_candidate

    # ============================================================================
    # COMMAND METHOD - Tag Mentions Updated
    # ============================================================================
    class TagMentionsUpdated(Aggregate.Event):
        tag_mentions: list[TagMention]

    def update_tag_mentions(self, tag_mentions: list[TagMention]) -> None:
        if self.is_deleted:
            msg = "Cannot update tag mentions on a deleted artifact"
            raise ValueError(msg)
        self.trigger_event(self.TagMentionsUpdated, tag_mentions=tag_mentions)

    @event(TagMentionsUpdated)
    def _apply_tag_mentions_updated(self, tag_mentions: list[TagMention]) -> None:
        self.tag_mentions = tag_mentions

    # ============================================================================
    # COMMAND METHOD - Author Mentions Updated
    # ============================================================================
    class AuthorMentionsUpdated(Aggregate.Event):
        author_mentions: list[AuthorMention]

    def update_author_mentions(self, author_mentions: list[AuthorMention]) -> None:
        if self.is_deleted:
            msg = "Cannot update author mentions on a deleted artifact"
            raise ValueError(msg)
        self.trigger_event(self.AuthorMentionsUpdated, author_mentions=author_mentions)

    @event(AuthorMentionsUpdated)
    def _apply_author_mentions_updated(self, author_mentions: list[AuthorMention]) -> None:
        self.author_mentions = author_mentions

    # ============================================================================
    # COMMAND METHOD - Presentation Date Updated
    # ============================================================================
    class PresentationDateUpdated(Aggregate.Event):
        presentation_date: PresentationDate | None

    def update_presentation_date(self, presentation_date: PresentationDate | None) -> None:
        if self.is_deleted:
            msg = "Cannot update presentation date on a deleted artifact"
            raise ValueError(msg)
        self.trigger_event(self.PresentationDateUpdated, presentation_date=presentation_date)

    @event(PresentationDateUpdated)
    def _apply_presentation_date_updated(self, presentation_date: PresentationDate | None) -> None:
        self.presentation_date = presentation_date

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
