"""Tests for deterministic page IDs (retry-safe creation)."""

from uuid import uuid4

from domain.aggregates.page import Page


def test_create_with_explicit_id_uses_it():
    pid, aid = uuid4(), uuid4()
    page = Page.create(name="Page 1", artifact_id=aid, index=0, page_id=pid)
    assert page.id == pid


def test_create_without_id_autogenerates():
    page = Page.create(name="Page 1", artifact_id=uuid4(), index=0)
    assert page.id is not None
