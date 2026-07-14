"""Tests for human-in-the-loop metadata corrections on the Artifact aggregate."""

from datetime import UTC, datetime

import pytest

from domain.aggregates.artifact import Artifact
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.presentation_date import PresentationDate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.title_mention import TitleMention


def make_artifact() -> Artifact:
    return Artifact.create(
        source_uri=None,
        source_filename="deck.pdf",
        artifact_type=ArtifactType.SCIENTIFIC_PRESENTATION,
        mime_type=MimeType.PDF,
        storage_location="blobs/deck.pdf",
    )


def test_correct_metadata_updates_values_and_records_provenance():
    artifact = make_artifact()
    corrected = artifact.correct_metadata(
        corrected_by_id="u-1",
        corrected_by_name="Siddhant Rath",
        title_mention=TitleMention(title="Corrected Title"),
    )
    assert corrected == ["title_mention"]
    assert artifact.title_mention.title == "Corrected Title"
    assert artifact.human_corrections["title_mention"]["corrected_by_id"] == "u-1"
    assert artifact.human_corrections["title_mention"]["corrected_by_name"] == "Siddhant Rath"
    assert isinstance(artifact.human_corrections["title_mention"]["corrected_at"], datetime)
    events = artifact.collect_events()
    assert [type(e).__name__ for e in events[-2:]] == [
        "TitleMentionUpdated",
        "HumanCorrectionRecorded",
    ]


def test_correct_metadata_multiple_fields_one_provenance_event():
    artifact = make_artifact()
    corrected = artifact.correct_metadata(
        corrected_by_id="u-1",
        corrected_by_name=None,
        tag_mentions=[TagMention(tag="rho kinase")],
        presentation_date=PresentationDate(date=datetime(2026, 1, 5, tzinfo=UTC), source="human"),
    )
    assert corrected == ["tag_mentions", "presentation_date"]
    names = [type(e).__name__ for e in artifact.collect_events()]
    assert names.count("HumanCorrectionRecorded") == 1


def test_machine_update_skipped_after_human_correction():
    artifact = make_artifact()
    artifact.correct_metadata(
        corrected_by_id="u-1",
        corrected_by_name=None,
        title_mention=TitleMention(title="Human Title"),
    )
    artifact.update_title_mention(TitleMention(title="Machine Title"))  # must silently no-op
    assert artifact.title_mention.title == "Human Title"


def test_machine_update_untouched_fields_still_work():
    artifact = make_artifact()
    artifact.correct_metadata(
        corrected_by_id="u-1",
        corrected_by_name=None,
        title_mention=TitleMention(title="Human Title"),
    )
    artifact.update_tag_mentions([TagMention(tag="machine tag")])
    assert artifact.tag_mentions[0].tag == "machine tag"


def test_recorrection_overwrites_provenance():
    artifact = make_artifact()
    artifact.correct_metadata(
        corrected_by_id="u-1", corrected_by_name="A", title_mention=TitleMention(title="T1")
    )
    artifact.correct_metadata(
        corrected_by_id="u-2", corrected_by_name="B", title_mention=TitleMention(title="T2")
    )
    assert artifact.title_mention.title == "T2"
    assert artifact.human_corrections["title_mention"]["corrected_by_id"] == "u-2"


def test_correct_metadata_noop_when_no_fields_given():
    artifact = make_artifact()
    artifact.collect_events()  # drain
    assert artifact.correct_metadata(corrected_by_id="u-1", corrected_by_name=None) == []
    assert artifact.collect_events() == []


def test_correct_metadata_can_clear_date():
    artifact = make_artifact()
    artifact.update_presentation_date(PresentationDate(date=datetime(2020, 1, 1, tzinfo=UTC)))
    artifact.correct_metadata(corrected_by_id="u-1", corrected_by_name=None, presentation_date=None)
    assert artifact.presentation_date is None
    assert "presentation_date" in artifact.human_corrections


def test_correct_metadata_rejected_on_deleted_artifact():
    artifact = make_artifact()
    artifact.delete()
    with pytest.raises(ValueError, match="deleted"):
        artifact.correct_metadata(
            corrected_by_id="u-1", corrected_by_name=None, title_mention=TitleMention(title="X")
        )


def test_replay_reconstructs_human_corrections():
    artifact = make_artifact()
    artifact.correct_metadata(
        corrected_by_id="u-1", corrected_by_name="A", title_mention=TitleMention(title="T1")
    )
    events = artifact.collect_events()
    replayed = None
    for e in events:
        replayed = e.mutate(replayed)
    assert replayed.human_corrections["title_mention"]["corrected_by_id"] == "u-1"
    replayed.update_title_mention(TitleMention(title="Machine"))
    assert replayed.title_mention.title == "T1"
