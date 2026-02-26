"""Tests for infrastructure components."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.mime_type import MimeType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from domain.value_objects.title_mention import TitleMention
from domain.value_objects.workflow_state import WorkflowState
from domain.value_objects.workflow_status import WorkflowStatus
from infrastructure.event_projectors.artifact_projector import ArtifactProjector
from infrastructure.event_projectors.event_projector import EventProjector
from infrastructure.event_projectors.page_projector import PageProjector
from infrastructure.serialization.pydantic_transcoder import PydanticTranscoding


class FakeMaterializer:
    def __init__(self) -> None:
        self.upsert_artifact_calls: list[tuple[str, dict, object]] = []
        self.upsert_page_calls: list[tuple[str, dict, object]] = []
        self.delete_artifact_calls: list[tuple[str, object]] = []
        self.delete_page_calls: list[tuple[str, object]] = []

    def upsert_artifact(self, artifact_id: str, fields: dict, tracking: object) -> None:
        self.upsert_artifact_calls.append((artifact_id, fields, tracking))

    def upsert_page(self, page_id: str, fields: dict, tracking: object) -> None:
        self.upsert_page_calls.append((page_id, fields, tracking))

    def delete_artifact(self, artifact_id: str, tracking: object) -> None:
        self.delete_artifact_calls.append((artifact_id, tracking))

    def delete_page(self, page_id: str, tracking: object) -> None:
        self.delete_page_calls.append((page_id, tracking))


def _tracking() -> object:
    return SimpleNamespace(notification_id=1)


class TestPydanticTranscoding:
    """Test PydanticTranscoding for event serialization."""

    def test_pydantic_transcoding_with_value_object(self, sample_title_mention) -> None:
        """Test PydanticTranscoding with a value object."""
        # Create transcoding for TitleMention
        transcoding = PydanticTranscoding(type(sample_title_mention))

        # Encode the value object
        encoded = transcoding.encode(sample_title_mention)
        assert isinstance(encoded, dict)
        assert encoded["title"] == sample_title_mention.title

        # Decode back
        decoded = transcoding.decode(encoded)
        assert decoded.title == sample_title_mention.title
        assert decoded.confidence == sample_title_mention.confidence

    def test_pydantic_transcoding_with_summary_candidate(
        self,
        sample_summary_candidate,
    ) -> None:
        """Test PydanticTranscoding with SummaryCandidate."""
        transcoding = PydanticTranscoding(type(sample_summary_candidate))

        encoded = transcoding.encode(sample_summary_candidate)
        assert isinstance(encoded, dict)
        assert encoded["summary"] == sample_summary_candidate.summary

        decoded = transcoding.decode(encoded)
        assert decoded == sample_summary_candidate


class TestEventProjector:
    """Test event projectors for building read models."""

    def test_artifact_projector_created_pages_and_tags(self) -> None:
        materializer = FakeMaterializer()
        projector = ArtifactProjector(materializer)

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        created_event = list(artifact.collect_events())[0]

        projector.artifact_created(created_event, _tracking())

        assert len(materializer.upsert_artifact_calls) == 1
        artifact_id, fields, _ = materializer.upsert_artifact_calls[0]
        assert artifact_id == str(created_event.originator_id)
        assert fields["source_uri"] == "https://example.com/paper.pdf"
        assert fields["source_filename"] == "paper.pdf"
        assert fields["pages"] == []
        assert fields["tags"] == []
        assert fields["title_mention"] is None

    def test_artifact_projector_pages_added_and_removed(self) -> None:
        materializer = FakeMaterializer()
        projector = ArtifactProjector(materializer)

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        list(artifact.collect_events())

        page_ids = [uuid4(), uuid4()]
        artifact.add_pages(page_ids)
        pages_added = list(artifact.collect_events())[0]

        projector.pages_added(pages_added, _tracking())

        artifact.remove_pages([page_ids[0]])
        pages_removed = list(artifact.collect_events())[0]

        projector.pages_removed(pages_removed, _tracking())

        assert materializer.upsert_artifact_calls[0][1]["pages"] == [
            str(page_ids[0]),
            str(page_ids[1]),
        ]
        assert materializer.upsert_artifact_calls[1][1]["pages"] == [str(page_ids[0])]

    def test_artifact_projector_mentions_and_delete(self) -> None:
        materializer = FakeMaterializer()
        projector = ArtifactProjector(materializer)

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        list(artifact.collect_events())

        title = TitleMention(title="Title", confidence=0.9)
        artifact.update_title_mention(title)
        title_event = list(artifact.collect_events())[0]
        projector.title_mention_updated(title_event, _tracking())

        summary = SummaryCandidate(summary="Summary", confidence=0.8)
        artifact.update_summary_candidate(summary)
        summary_event = list(artifact.collect_events())[0]
        projector.summary_candidate_updated(summary_event, _tracking())

        artifact.update_tags(["chemistry"])
        tags_event = list(artifact.collect_events())[0]
        projector.tags_updated(tags_event, _tracking())

        artifact.delete()
        deleted_event = list(artifact.collect_events())[0]
        projector.artifact_deleted(deleted_event, _tracking())

        assert materializer.upsert_artifact_calls[0][1]["title_mention"]["title"] == "Title"
        assert materializer.upsert_artifact_calls[1][1]["summary_candidate"]["summary"] == "Summary"
        assert materializer.upsert_artifact_calls[2][1]["tags"] == ["chemistry"]
        assert materializer.delete_artifact_calls[0][0] == str(deleted_event.originator_id)

    def test_artifact_projector_workflow_status_updated(self) -> None:
        materializer = FakeMaterializer()
        projector = ArtifactProjector(materializer)

        artifact = Artifact.create(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        list(artifact.collect_events())

        status = WorkflowStatus(state=WorkflowState.PENDING, message="queued")
        artifact.update_workflow_status("extract", status)
        status_event = list(artifact.collect_events())[0]

        projector.workflow_status_updated(status_event, _tracking())

        _, fields, _ = materializer.upsert_artifact_calls[0]
        assert fields["workflow_statuses.extract"]["state"] == "PENDING"
        assert fields["workflow_statuses.extract"]["message"] == "queued"

    def test_page_projector_events(self) -> None:
        materializer = FakeMaterializer()
        projector = PageProjector(materializer)

        page = Page.create(name="Intro", artifact_id=uuid4(), index=0)
        created_event = list(page.collect_events())[0]
        projector.page_created(created_event, _tracking())

        compound = CompoundMention(smiles="C", extracted_id="Test")
        page.update_compound_mentions([compound])
        compound_event = list(page.collect_events())[0]
        projector.compound_mentions_updated(compound_event, _tracking())

        tag = TagMention(tag="chemistry", confidence=0.9)
        page.update_tag_mentions([tag])
        tag_event = list(page.collect_events())[0]
        projector.tag_mentions_updated(tag_event, _tracking())

        text = TextMention(text="Note", confidence=0.7)
        page.update_text_mention(text)
        text_event = list(page.collect_events())[0]
        projector.text_mention_updated(text_event, _tracking())

        summary = SummaryCandidate(summary="Summary", confidence=0.8)
        page.update_summary_candidate(summary)
        summary_event = list(page.collect_events())[0]
        projector.summary_candidate_updated(summary_event, _tracking())

        page.delete()
        deleted_event = list(page.collect_events())[0]
        projector.page_deleted(deleted_event, _tracking())

        assert materializer.upsert_page_calls[0][1]["name"] == "Intro"
        assert materializer.upsert_page_calls[1][1]["compound_mentions"][0]["smiles"] == "C"
        assert materializer.upsert_page_calls[2][1]["tag_mentions"][0]["tag"] == "chemistry"
        assert materializer.upsert_page_calls[3][1]["text_mention"]["text"] == "Note"
        assert materializer.upsert_page_calls[4][1]["summary_candidate"]["summary"] == "Summary"
        assert materializer.delete_page_calls[0][0] == str(deleted_event.originator_id)

    def test_page_projector_workflow_status_updated(self) -> None:
        materializer = FakeMaterializer()
        projector = PageProjector(materializer)

        page = Page.create(name="Intro", artifact_id=uuid4(), index=0)
        list(page.collect_events())

        status = WorkflowStatus(state=WorkflowState.IN_PROGRESS, progress=0.4)
        page.update_workflow_status("ocr", status)
        status_event = list(page.collect_events())[0]

        projector.workflow_status_updated(status_event, _tracking())

        _, fields, _ = materializer.upsert_page_calls[0]
        assert fields["workflow_statuses.ocr"]["state"] == "IN_PROGRESS"
        assert fields["workflow_statuses.ocr"]["progress"] == 0.4

    def test_event_projector_routes_and_ignores_unknown_events(self) -> None:
        materializer = FakeMaterializer()
        projector = EventProjector(materializer)

        page = Page.create(name="Intro", artifact_id=uuid4(), index=0)
        created_event = list(page.collect_events())[0]

        projector.process_event(created_event, _tracking())

        class UnknownEvent:
            pass

        projector.process_event(UnknownEvent(), _tracking())

        assert len(materializer.upsert_page_calls) == 1


class TestEventSourcedRepository:
    """Test event sourced repositories."""


class TestReadModelMaterializer:
    """Test read model materializer."""
