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

        source_uri = source_uri.strip()
        source_filename = source_filename.strip()
        storage_location = storage_location.strip()

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
        self.source_uri = source_uri
        self.source_filename = source_filename
        self.artifact_type = artifact_type
        self.mime_type = mime_type
        self.storage_location = storage_location
        self._pages: list[UUID] = []
        self.title_mention: TitleMention | None = None
        self.summary_candidate: SummaryCandidate | None = None
        self.tags: set[str] = set()

    def __hash__(self) -> int:
        """Return hash of the aggregate based on its ID."""
        return hash(self.id)

    # ============================================================================
    # COMMAND METHOD - Page Management
    # ============================================================================
    @property
    def pages(self) -> list[UUID]:
        """Returns the list of associated Page IDs."""
        return self._pages

    class PagesAdded(Aggregate.Event):
        page_ids: list[UUID]

    def add_pages(self, page_ids: list[UUID]) -> None:
        """Add associated Page IDs to the Artifact."""
        self.trigger_event(self.PagesAdded, page_ids=page_ids)

    @event(PagesAdded)
    def _apply_pages_added(self, page_ids: list[UUID]) -> None:
        self._pages.extend(page_ids)

    class PagesRemoved(Aggregate.Event):
        page_ids: list[UUID]

    def remove_pages(self, page_ids: list[UUID]) -> None:
        """Remove associated Page IDs from the Artifact."""
        self.trigger_event(self.PagesRemoved, page_ids=page_ids)

    @event(PagesRemoved)
    def _apply_pages_removed(self, page_ids: list[UUID]) -> None:
        self._pages = [pid for pid in self._pages if pid not in page_ids]

    # ============================================================================
    # COMMAND METHOD - Update TitleMention
    # ============================================================================
    class TitleMentionUpdated(Aggregate.Event):
        title_mention: TitleMention

    def update_title_mention(self, title_mention: TitleMention) -> None:
        self.trigger_event(self.TitleMentionUpdated, title_mention=title_mention)

    @event(TitleMentionUpdated)
    def _apply_title_mention_updated(self, title_mention: TitleMention) -> None:
        self.title_mention = title_mention

    # ============================================================================
    # COMMAND METHOD - update SummaryCandidate
    # ============================================================================
    class SummaryCandidateUpdated(Aggregate.Event):
        summary_candidate: SummaryCandidate

    def update_summary_candidate(self, summary_candidate: SummaryCandidate) -> None:
        self.trigger_event(self.SummaryCandidateUpdated, summary_candidate=summary_candidate)

    @event(SummaryCandidateUpdated)
    def _apply_summary_candidate_updated(self, summary_candidate: SummaryCandidate) -> None:
        self.summary_candidate = summary_candidate

    # ============================================================================
    # COMMAND METHOD - Tag Updated
    # ============================================================================
    class TagsUpdated(Aggregate.Event):
        tags: set[str]

    def update_tags(self, tags: set[str]) -> None:
        self.trigger_event(self.TagsUpdated, tags=tags)

    @event(TagsUpdated)
    def _apply_tags_updated(self, tags: set[str]) -> None:
        self.tags = tags
