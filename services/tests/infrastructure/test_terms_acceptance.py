"""Terms/Privacy acceptance: store semantics + the gate's required/not-required call.

No DB — a fake collection covering the two operations the store performs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from application.dtos.user_dtos import TermsAcceptanceDTO
from interfaces.api.routes.helpers import ensure_terms_accepted
from interfaces.api.routes.user_routes import _terms_status

VERSION = "2026-08-28"


class _FakeTermsColl:
    """Just enough of a Mongo collection for get/record acceptance."""

    def __init__(self) -> None:
        self.docs: list[dict] = []

    async def find_one(self, q: dict, sort=None) -> dict | None:
        hits = [d for d in self.docs if all(d.get(k) == v for k, v in q.items())]
        if not hits:
            return None
        return max(hits, key=lambda d: d["accepted_at"])

    async def find_one_and_update(
        self, q: dict, update: dict, upsert: bool = False, return_document=None
    ) -> dict:
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return d  # $setOnInsert is a no-op on an existing doc
        doc = {**q, **update["$setOnInsert"]}
        self.docs.append(doc)
        return doc

    async def create_indexes(self, models: list) -> None:
        return None


def _make_store():
    from infrastructure.read_repositories.mongo_user_store import MongoUserStore

    store = MongoUserStore.__new__(MongoUserStore)
    store.terms_acceptance = _FakeTermsColl()
    return store


class _Settings:
    def __init__(self, *, self_serve: bool, version: str = VERSION) -> None:
        self.self_serve_enabled = self_serve
        self.terms_version = version


class _Auth:
    def __init__(self) -> None:
        self.user_id = uuid4()


class _Container:
    """Maps the two port lookups `_terms_status`/`ensure_terms_accepted` make."""

    def __init__(self, settings, store) -> None:
        self._settings = settings
        self._store = store

    def __getitem__(self, key):
        from application.ports.repositories.terms_acceptance_store import (
            TermsAcceptanceStore,
        )
        from infrastructure.config import Settings

        if key is Settings:
            return self._settings
        if key is TermsAcceptanceStore:
            return self._store
        raise KeyError(key)


# ── store ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_acceptance_returns_none() -> None:
    store = _make_store()
    assert await store.get_acceptance(uuid4()) is None


@pytest.mark.asyncio
async def test_record_then_read_round_trips() -> None:
    store, user = _make_store(), uuid4()
    written = await store.record_acceptance(user, VERSION)
    read = await store.get_acceptance(user)
    assert isinstance(written, TermsAcceptanceDTO)
    assert read is not None
    assert read.version == VERSION
    assert read.accepted_at == written.accepted_at


@pytest.mark.asyncio
async def test_re_accepting_keeps_the_original_timestamp() -> None:
    """The first acceptance is the evidence; a second click must not overwrite it."""
    store, user = _make_store(), uuid4()
    first = await store.record_acceptance(user, VERSION)
    again = await store.record_acceptance(user, VERSION)
    assert again.accepted_at == first.accepted_at
    assert len(store.terms_acceptance.docs) == 1


@pytest.mark.asyncio
async def test_a_new_version_is_a_separate_record() -> None:
    store, user = _make_store(), uuid4()
    await store.record_acceptance(user, "2026-08-28")
    await store.record_acceptance(user, "2027-01-01")
    assert len(store.terms_acceptance.docs) == 2
    latest = await store.get_acceptance(user)
    assert latest is not None


# ── gate ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gate_is_off_when_self_serve_is_off() -> None:
    """Internal and consortium deployments have their own agreements."""
    store, auth = _make_store(), _Auth()
    container = _Container(_Settings(self_serve=False), store)
    status = await _terms_status(container, auth)
    assert status.required is False
    await ensure_terms_accepted(auth, container)  # must not raise


@pytest.mark.asyncio
async def test_gate_required_until_accepted() -> None:
    store, auth = _make_store(), _Auth()
    container = _Container(_Settings(self_serve=True), store)

    assert (await _terms_status(container, auth)).required is True
    with pytest.raises(Exception) as exc:
        await ensure_terms_accepted(auth, container)
    assert exc.value.status_code == 451

    await store.record_acceptance(auth.user_id, VERSION)
    assert (await _terms_status(container, auth)).required is False
    await ensure_terms_accepted(auth, container)  # must not raise


@pytest.mark.asyncio
async def test_bumping_the_version_re_gates_an_accepted_user() -> None:
    """Change the terms and prior acceptance stops counting."""
    store, auth = _make_store(), _Auth()
    await store.record_acceptance(auth.user_id, "2026-08-28")

    container = _Container(_Settings(self_serve=True, version="2027-01-01"), store)
    status = await _terms_status(container, auth)
    assert status.required is True
    assert status.accepted_version == "2026-08-28"
    with pytest.raises(Exception) as exc:
        await ensure_terms_accepted(auth, container)
    assert exc.value.status_code == 451


@pytest.mark.asyncio
async def test_status_reports_what_was_accepted() -> None:
    store, auth = _make_store(), _Auth()
    before = datetime.now(UTC)
    await store.record_acceptance(auth.user_id, VERSION)
    status = await _terms_status(_Container(_Settings(self_serve=True), store), auth)
    assert status.accepted_version == VERSION
    assert status.accepted_at is not None
    assert status.accepted_at >= before
