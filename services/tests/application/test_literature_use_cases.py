"""Ingesting a paper: what gets refused, what gets skipped, what gets kept.

The hits are the real Europe PMC fixture, so the licence cases under test are
records that actually exist rather than ones invented to suit the code.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from returns.result import Failure, Success

from application.use_cases.literature_use_cases import IngestLiteratureUseCase
from domain.value_objects.source_class import SourceClass
from infrastructure.literature.europe_pmc import (
    LiteratureHit,
    LiteratureSourceUnavailableError,
    parse_hit,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "europe_pmc_search_core.json"

CC_BY = "41591406"  # ingestable
ND = "40687024"  # open access, but no derivatives


@pytest.fixture
def hits() -> dict[str, LiteratureHit]:
    records = json.loads(FIXTURE.read_text())["resultList"]["result"]
    return {h.external_id: h for h in (parse_hit(r) for r in records)}


class FakeClient:
    def __init__(self, hit: LiteratureHit | None, pdf: bytes | None = b"%PDF-1.7 fake") -> None:
        self._hit = hit
        self._pdf = pdf
        self.pdf_fetches = 0

    async def fetch_one(self, source: str, external_id: str) -> LiteratureHit | None:
        return self._hit

    async def fetch_pdf(self, hit: LiteratureHit) -> bytes | None:
        self.pdf_fetches += 1
        return self._pdf


class FakeReadModel:
    def __init__(self, existing: UUID | None = None) -> None:
        self._existing = existing
        self.queried: list[str] = []

    async def find_artifact_id_by_source_uri(
        self,
        source_uri: str,
        workspace_id: UUID | None = None,
    ) -> UUID | None:
        self.queried.append(source_uri)
        return self._existing


class FakeSaga:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute(self, stream, upload_req, auth=None):
        self.calls.append({"body": stream.read(), "req": upload_req, "auth": auth})
        return Success("ingested")


def _use_case(client, saga, read_model) -> IngestLiteratureUseCase:
    return IngestLiteratureUseCase(
        client=client,
        upload_saga=saga,
        artifact_read_model=read_model,
    )


async def test_an_open_licence_reaches_the_saga_as_a_normal_upload(hits):
    client, saga = FakeClient(hits[CC_BY]), FakeSaga()
    result = await _use_case(client, saga, FakeReadModel()).execute(
        source="MED",
        external_id=CC_BY,
    )

    assert isinstance(result, Success)
    req = saga.calls[0]["req"]
    assert saga.calls[0]["body"] == b"%PDF-1.7 fake"
    assert req.source_class == SourceClass.LITERATURE_OA
    assert req.licence == "cc by"
    assert req.mime_type == "application/pdf"
    # The DOI, not a Europe PMC id: it is what dedup matches on next time, and
    # what a reader following the citation should land on.
    assert req.source_uri == "https://doi.org/10.1021/acs.jmedchem.5c02409"


async def test_no_derivatives_is_refused_and_never_fetched(hits):
    client, saga = FakeClient(hits[ND]), FakeSaga()
    result = await _use_case(client, saga, FakeReadModel()).execute(source="MED", external_id=ND)

    assert isinstance(result, Failure)
    assert result.failure().category == "forbidden"
    assert "derivative" in result.failure().message
    assert client.pdf_fetches == 0, "refused papers must not be downloaded at all"
    assert saga.calls == []


async def test_a_paper_already_here_is_a_conflict_not_a_second_copy(hits):
    existing = uuid4()
    client, saga = FakeClient(hits[CC_BY]), FakeSaga()
    result = await _use_case(client, saga, FakeReadModel(existing)).execute(
        source="MED",
        external_id=CC_BY,
    )

    assert isinstance(result, Failure)
    assert result.failure().category == "conflict"
    assert str(existing) in result.failure().message
    # The point of the check is the work it avoids, so assert the work.
    assert client.pdf_fetches == 0
    assert saga.calls == []


async def test_dedup_matches_on_the_same_uri_that_gets_stored(hits):
    """Otherwise the second ingest never matches the first and duplicates forever."""
    read_model = FakeReadModel()
    saga = FakeSaga()
    await _use_case(FakeClient(hits[CC_BY]), saga, read_model).execute(
        source="MED",
        external_id=CC_BY,
    )
    assert read_model.queried == [saga.calls[0]["req"].source_uri]


async def test_an_unknown_record_is_not_found():
    result = await _use_case(FakeClient(None), FakeSaga(), FakeReadModel()).execute(
        source="MED",
        external_id="99999999",
    )
    assert isinstance(result, Failure)
    assert result.failure().category == "not_found"


async def test_a_missing_pdf_does_not_create_an_empty_artifact(hits):
    saga = FakeSaga()
    result = await _use_case(FakeClient(hits[CC_BY], pdf=None), saga, FakeReadModel()).execute(
        source="MED",
        external_id=CC_BY,
    )
    assert isinstance(result, Failure)
    assert saga.calls == []


async def test_an_unreachable_source_is_not_reported_as_a_missing_paper(hits):
    """Europe PMC 503s often enough that this distinction is not academic.

    Collapsing the two tells someone their paper does not exist when it does,
    and it is a claim they cannot check from the UI.
    """

    class DeadClient(FakeClient):
        async def fetch_one(self, source, external_id):
            raise LiteratureSourceUnavailableError("503")

    saga = FakeSaga()
    result = await _use_case(DeadClient(hits[CC_BY]), saga, FakeReadModel()).execute(
        source="MED",
        external_id=CC_BY,
    )
    assert isinstance(result, Failure)
    assert result.failure().category == "infrastructure"
    assert "unavailable" in result.failure().message
    assert saga.calls == []
