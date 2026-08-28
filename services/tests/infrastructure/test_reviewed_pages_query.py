"""The export query filter. Pure dict-building, so it is testable without Mongo."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from infrastructure.read_repositories.cser_export_query import build_cser_export_query

WORKSPACE = UUID("55555555-5555-5555-5555-555555555555")
SINCE = datetime(2026, 8, 1, tzinfo=UTC)


def test_reviewed_filter_keys_on_the_correction_existing():
    query = build_cser_export_query(WORKSPACE, only_reviewed=True, since=None)

    assert query["human_corrections.compound_mentions"] == {"$exists": True}
    # Crucially, NOT a filter on compound_mentions: a page corrected to an
    # empty list is a reviewed negative the detector needs.
    assert "compound_mentions" not in query


def test_reviewed_filter_scopes_to_the_workspace():
    query = build_cser_export_query(WORKSPACE, only_reviewed=True, since=None)

    assert query["workspace_id"] == str(WORKSPACE)
    # No is_deleted clause: deletion is a hard delete_one on the read model,
    # so a deleted page is already absent from the collection. A filter term
    # on a field that never exists would just be dead weight.
    assert "is_deleted" not in query


def test_since_filters_on_the_correction_timestamp_as_an_iso_string():
    query = build_cser_export_query(WORKSPACE, only_reviewed=True, since=SINCE)

    # corrected_at is stored by the projector as `.isoformat()` — a STRING,
    # not a BSON date. Mongo never equates a date to a string, so comparing
    # with a raw datetime here would silently match zero documents. Do NOT
    # "helpfully" change this back to `SINCE` (a datetime) — ISO-8601 sorts
    # lexicographically in chronological order, so the string form is
    # correct for $gte, and the raw-datetime form is the bug this guards.
    value = query["human_corrections.compound_mentions.corrected_at"]
    assert value == {"$gte": SINCE.isoformat()}
    assert isinstance(value["$gte"], str)


def test_since_is_ignored_when_not_filtering_to_reviewed_pages():
    # Machine pages have no correction timestamp to compare against.
    query = build_cser_export_query(WORKSPACE, only_reviewed=False, since=SINCE)

    assert not any(key.startswith("human_corrections") for key in query)


def test_bootstrap_mode_takes_any_page_that_has_mentions():
    query = build_cser_export_query(WORKSPACE, only_reviewed=False, since=None)

    assert query["compound_mentions"] == {"$exists": True, "$ne": []}


def test_restricted_artifact_visibility_is_carried_into_the_filter():
    # `artifacts:hiledit` is not "see every document": the export must be
    # scoped to the artifacts this caller can view, or it hands out every
    # render, SMILES and coordinate set in the workspace.
    allowed = [UUID("11111111-1111-1111-1111-111111111111")]

    query = build_cser_export_query(
        WORKSPACE, only_reviewed=True, since=None, allowed_artifact_ids=allowed
    )

    # Stored as a string on the page document, not a UUID.
    assert query["artifact_id"] == {"$in": [str(allowed[0])]}


def test_full_access_adds_no_artifact_clause():
    # get_allowed_artifact_ids returns None for full access (and when Duar is
    # down); None must mean "no extra filter", never "match nothing".
    query = build_cser_export_query(
        WORKSPACE, only_reviewed=True, since=None, allowed_artifact_ids=None
    )

    assert "artifact_id" not in query
