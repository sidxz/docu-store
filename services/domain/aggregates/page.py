from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from eventsourcing.domain import Aggregate, event

if TYPE_CHECKING:
    from uuid import UUID

    from domain.value_objects.compound_mention import CompoundMention
    from domain.value_objects.embedding_metadata import EmbeddingMetadata
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
        # Validate required fields (following same pattern as Artifact)
        if not name or not name.strip():
            msg = "name must be provided"
            raise ValueError(msg)
        if artifact_id is None:
            msg = "artifact_id must be provided"
            raise ValueError(msg)
        if index < 0:
            msg = "index must be non-negative"
            raise ValueError(msg)

        self.name = name.strip()
        self.artifact_id = artifact_id
        self.index = index
        self.compound_mentions: list[CompoundMention] = []
        self.tag_mentions: list[TagMention] = []
        self.text_mention: TextMention | None = None
        self.summary_candidate: SummaryCandidate | None = None
        self.text_embedding_metadata: EmbeddingMetadata | None = None
        self.smiles_embedding_metadata: EmbeddingMetadata | None = None
        self.is_deleted: bool = False

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
        if self.is_deleted:
            msg = "Cannot update compound mentions on a deleted page"
            raise ValueError(msg)
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
        if self.is_deleted:
            msg = "Cannot update tag mentions on a deleted page"
            raise ValueError(msg)
        self.trigger_event(self.TagMentionsUpdated, tag_mentions=tag_mentions)

    @event(TagMentionsUpdated)
    def _apply_tag_mentions_updated(self, tag_mentions: list[TagMention]) -> None:
        self.tag_mentions = tag_mentions

    # ============================================================================
    # COMMAND METHOD - Update TextMention
    # ============================================================================
    class TextMentionUpdated(Aggregate.Event):
        text_mention: TextMention | None

    def update_text_mention(self, text_mention: TextMention | None) -> None:
        if self.is_deleted:
            msg = "Cannot update text mention on a deleted page"
            raise ValueError(msg)
        self.trigger_event(self.TextMentionUpdated, text_mention=text_mention)

    @event(TextMentionUpdated)
    def _apply_text_mention_updated(self, text_mention: TextMention | None) -> None:
        self.text_mention = text_mention

    # ============================================================================
    # COMMAND METHOD - update SummaryCandidate
    # ============================================================================
    class SummaryCandidateUpdated(Aggregate.Event):
        summary_candidate: SummaryCandidate | None

    def update_summary_candidate(self, summary_candidate: SummaryCandidate | None) -> None:
        if self.is_deleted:
            msg = "Cannot update summary candidate on a deleted page"
            raise ValueError(msg)
        self.trigger_event(self.SummaryCandidateUpdated, summary_candidate=summary_candidate)

    @event(SummaryCandidateUpdated)
    def _apply_summary_candidate_updated(self, summary_candidate: SummaryCandidate | None) -> None:
        self.summary_candidate = summary_candidate

    # ============================================================================
    # COMMAND METHOD - Update Text Embedding Metadata
    # ============================================================================
    class TextEmbeddingGenerated(Aggregate.Event):
        """Emitted when a text embedding is generated for this page."""

        embedding_metadata: EmbeddingMetadata

    def update_text_embedding_metadata(self, embedding_metadata: EmbeddingMetadata) -> None:
        """Update the page with generated embedding metadata.

        The actual embedding vector is stored in the vector store.
        This method only records metadata about the embedding in the domain.
        """
        if self.is_deleted:
            msg = "Cannot update embedding on a deleted page"
            raise ValueError(msg)
        self.trigger_event(self.TextEmbeddingGenerated, embedding_metadata=embedding_metadata)

    @event(TextEmbeddingGenerated)
    def _apply_text_embedding_generated(self, embedding_metadata: EmbeddingMetadata) -> None:
        self.text_embedding_metadata = embedding_metadata

    # ============================================================================
    # COMMAND METHOD - Update SMILES Embedding Metadata
    # ============================================================================
    class SmilesEmbeddingGenerated(Aggregate.Event):
        """Emitted when ChemBERTa SMILES embeddings are generated for this page."""

        embedding_metadata: EmbeddingMetadata

    def update_smiles_embedding_metadata(self, embedding_metadata: EmbeddingMetadata) -> None:
        """Record metadata about the SMILES embedding stored in the compound vector store."""
        if self.is_deleted:
            msg = "Cannot update embedding on a deleted page"
            raise ValueError(msg)
        self.trigger_event(self.SmilesEmbeddingGenerated, embedding_metadata=embedding_metadata)

    @event(SmilesEmbeddingGenerated)
    def _apply_smiles_embedding_generated(self, embedding_metadata: EmbeddingMetadata) -> None:
        self.smiles_embedding_metadata = embedding_metadata

    # ============================================================================
    # COMMAND METHOD - Delete Page
    # ============================================================================
    class Deleted(Aggregate.Event):
        deleted_at: datetime

    def delete(self) -> None:
        """Delete this page aggregate."""
        self.trigger_event(self.Deleted, deleted_at=datetime.now(UTC))

    @event(Deleted)
    def _apply_deleted(self, deleted_at: datetime) -> None:
        self.deleted_at = deleted_at
        self.is_deleted = True
