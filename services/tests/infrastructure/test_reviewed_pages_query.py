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


def test_reviewed_filter_scopes_to_the_workspace_and_skips_deleted():
    query = build_cser_export_query(WORKSPACE, only_reviewed=True, since=None)

    assert query["workspace_id"] == str(WORKSPACE)
    assert query["is_deleted"] == {"$ne": True}


def test_since_filters_on_the_correction_timestamp():
    query = build_cser_export_query(WORKSPACE, only_reviewed=True, since=SINCE)

    assert query["human_corrections.compound_mentions.corrected_at"] == {"$gte": SINCE}


def test_since_is_ignored_when_not_filtering_to_reviewed_pages():
    # Machine pages have no correction timestamp to compare against.
    query = build_cser_export_query(WORKSPACE, only_reviewed=False, since=SINCE)

    assert not any(key.startswith("human_corrections") for key in query)


def test_bootstrap_mode_takes_any_page_that_has_mentions():
    query = build_cser_export_query(WORKSPACE, only_reviewed=False, since=None)

    assert query["compound_mentions"] == {"$exists": True, "$ne": []}
