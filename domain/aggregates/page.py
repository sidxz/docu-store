from __future__ import annotations

from uuid import UUID

from eventsourcing.domain import Aggregate, event

from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention


class Page(Aggregate):
    """The Aggregate Root for a Page.

    It is now purely focused on domain logic and state transitions.
    """

    INITIAL_VERSION = 0

    @classmethod
    def create(cls, name: str, artifact_id: UUID, index: int = 0) -> Page:
        """Create a new Page aggregate (Factory Method)."""
        return cls(name=name, artifact_id=artifact_id, index=index)

    class Created(Aggregate.Created):
        """Defines the structure of the Page Created event."""

        name: str
        artifact_id: UUID
        index: int

    @event(Created)  # Links this handler to the Created event class above
    def __init__(self, name: str, artifact_id: UUID, index: int) -> None:
        self.name = name
        self.artifact_id = artifact_id
        self.index = index
        self.compound_mentions: list[CompoundMention] = []
        self.tag_mentions: list[TagMention] = []
        self.text_mention: TextMention | None = None
        self.summary_candidate: SummaryCandidate | None = None

    def __hash__(self) -> int:
        """Return hash of the aggregate based on its ID."""
        return hash(self.id)

    # ============================================================================
    # COMMAND METHOD - Update CompoundMentions
    # ============================================================================
    class CompoundMentionsUpdated(Aggregate.Event):
        # We use the rich type here. The infrastructure layer
        # (transcoder) will handle the JSON serialization.
        compound_mentions: list[CompoundMention]

    def update_compound_mentions(self, compound_mentions: list[CompoundMention]) -> None:
        # Trigger event
        self.trigger_event(self.CompoundMentionsUpdated, compound_mentions=compound_mentions)

    @event(CompoundMentionsUpdated)
    def _apply_compound_mentions_updated(self, compound_mentions: list[CompoundMention]) -> None:
        # Update internal state, replace existing compound_mentions
        self.compound_mentions = compound_mentions

    # ============================================================================
    # COMMAND METHOD - Update TagMentions
    # ============================================================================
    class TagMentionsUpdated(Aggregate.Event):
        tag_mentions: list[TagMention]

    def update_tag_mentions(self, tag_mentions: list[TagMention]) -> None:
        self.trigger_event(self.TagMentionsUpdated, tag_mentions=tag_mentions)

    @event(TagMentionsUpdated)
    def _apply_tag_mentions_updated(self, tag_mentions: list[TagMention]) -> None:
        self.tag_mentions = tag_mentions

    # ============================================================================
    # COMMAND METHOD - Update TextMention
    # ============================================================================
    class TextMentionUpdated(Aggregate.Event):
        text_mention: TextMention

    def update_text_mention(self, text_mention: TextMention) -> None:
        self.trigger_event(self.TextMentionUpdated, text_mention=text_mention)

    @event(TextMentionUpdated)
    def _apply_text_mention_updated(self, text_mention: TextMention) -> None:
        self.text_mention = text_mention

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
