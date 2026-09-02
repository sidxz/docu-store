"""Parsing Europe PMC, and deciding what may be kept from it.

The fixture is ten real records from one query (`InhA` + `inhibitor`), kept
because three of them break the rule anyone would write first. `isOpenAccess`
is not the ingest gate; the licence is.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from infrastructure.literature import europe_pmc as epmc
from infrastructure.literature.europe_pmc import (
    EuropePmcClient,
    LiteratureHit,
    LiteratureQueryError,
    LiteratureSourceUnavailableError,
    parse_hit,
    strip_markup,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "europe_pmc_search_core.json"


@pytest.fixture
def hits() -> dict[str, LiteratureHit]:
    records = json.loads(FIXTURE.read_text())["resultList"]["result"]
    return {h.external_id: h for h in (parse_hit(r) for r in records)}


def test_parses_every_record_in_the_fixture(hits):
    assert len(hits) == 10
    article = hits["41591406"]
    assert article.title
    assert article.doi == "10.1021/acs.jmedchem.5c02409"
    assert article.pmcid == "PMC12910649"
    assert article.journal
    assert article.year == 2026
    assert article.abstract


def test_cc_by_with_full_text_is_ingestable(hits):
    article = hits["41591406"]
    assert article.licence == "cc by"
    assert article.ingest_blocker() is None
    assert article.is_ingestable


def test_non_commercial_is_still_ingestable(hits):
    # NC restricts commercial *use*, not derivative works. A research workspace
    # keeping a copy is squarely inside it.
    article = hits["40901448"]
    assert article.licence == "cc by-nc"
    assert article.is_ingestable


def test_no_derivatives_is_refused_despite_being_open_access(hits):
    # The case that makes isOpenAccess the wrong gate in one direction: Europe
    # PMC calls this open, and chunking it would still be a derivative work.
    article = hits["40687024"]
    assert article.is_open_access is True
    assert article.licence == "cc by-nc-nd"
    assert not article.is_ingestable
    assert "derivative" in article.ingest_blocker()


def test_unlicensed_full_text_is_refused(hits):
    # And the other direction: Europe PMC holds the full text (inEPMC=Y) under
    # no licence at all. Free to read is not free to mine.
    article = hits["37270808"]
    assert article.is_open_access is False
    assert article.in_epmc is True
    assert article.licence is None
    assert not article.is_ingestable
    assert "no open licence" in article.ingest_blocker()


def test_cc_by_preprint_is_blocked_on_availability_not_licence(hits):
    # isOpenAccess=N, yet CC BY. The licence permits keeping it; Europe PMC
    # simply has no full text to give us. The distinction is what the UI shows.
    preprint = hits["PPR1298287"]
    assert preprint.source == "PPR"
    assert preprint.is_open_access is False
    assert preprint.licence == "cc by"
    assert not preprint.is_ingestable
    assert "full text" in preprint.ingest_blocker()


def test_url_prefers_the_publisher_copy(hits):
    assert hits["41591406"].url == "https://doi.org/10.1021/acs.jmedchem.5c02409"


def test_url_falls_back_to_europe_pmc_without_a_doi():
    hit = LiteratureHit(external_id="12345", source="MED", title="No DOI here")
    assert hit.url == "https://europepmc.org/article/MED/12345"


async def test_fetch_pdf_refuses_before_touching_the_network(hits):
    # The refusal has to land in the client, not only in the UI: a caller that
    # skipped is_ingestable must still not be able to pull bytes we may not keep.
    assert await EuropePmcClient().fetch_pdf(hits["40687024"]) is None


async def test_search_returns_empty_when_europe_pmc_is_unreachable(monkeypatch):
    # Their API 503'd twice while this was being written. A dead source should
    # leave the chat able to say so, not error the turn.
    monkeypatch.setattr(epmc, "_RETRY_BACKOFF_SECONDS", 0.0)
    client = EuropePmcClient(search_url="http://127.0.0.1:9/search")
    assert await client.search("InhA") == []


class _FakeResponse:
    """Enough of httpx.Response for search_or_raise."""

    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {"resultList": {"result": []}}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Server error '{self.status_code}'",
                request=httpx.Request("GET", "http://test"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Replaces httpx.AsyncClient; yields one queued response per GET."""

    def __init__(self, statuses: list[int], payload: dict | None = None) -> None:
        self._statuses = list(statuses)
        self._payload = payload
        self.calls = 0

    def __call__(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN204
        return self

    async def __aenter__(self):  # noqa: ANN204
        return self

    async def __aexit__(self, *exc):  # noqa: ANN002, ANN204
        return False

    async def get(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN204
        self.calls += 1
        return _FakeResponse(self._statuses.pop(0), self._payload)


async def test_transient_5xx_is_retried_then_succeeds(monkeypatch):
    fake = _FakeAsyncClient([503, 502, 200])
    monkeypatch.setattr(epmc.httpx, "AsyncClient", fake, raising=False)
    monkeypatch.setattr(epmc, "_RETRY_BACKOFF_SECONDS", 0.0)

    hits = await EuropePmcClient().search_or_raise("TITLE_ABS:test")

    assert hits == []
    assert fake.calls == 3, "should have retried twice before succeeding"


async def test_persistent_5xx_still_raises(monkeypatch):
    fake = _FakeAsyncClient([503, 503, 503])
    monkeypatch.setattr(epmc.httpx, "AsyncClient", fake, raising=False)
    monkeypatch.setattr(epmc, "_RETRY_BACKOFF_SECONDS", 0.0)

    with pytest.raises(LiteratureSourceUnavailableError):
        await EuropePmcClient().search_or_raise("TITLE_ABS:test")

    assert fake.calls == 3, "should stop after _MAX_ATTEMPTS"


async def test_client_error_is_not_retried(monkeypatch):
    """A malformed query is 400 — retrying it is pure latency.

    And it is reported as a query error, not an outage: the outage wording tells
    the caller to send the same query again, which for a 400 never succeeds.
    """
    fake = _FakeAsyncClient([400, 200])
    monkeypatch.setattr(epmc.httpx, "AsyncClient", fake, raising=False)
    monkeypatch.setattr(epmc, "_RETRY_BACKOFF_SECONDS", 0.0)

    with pytest.raises(LiteratureQueryError):
        await EuropePmcClient().search_or_raise("TITLE_ABS:test")

    assert fake.calls == 1, "4xx must not be retried"


async def test_a_malformed_record_does_not_escape_as_a_bare_key_error(monkeypatch):
    """A 200 carrying a record without `id` is a bad response, not a crash."""
    fake = _FakeAsyncClient([200], {"resultList": {"result": [{"source": "MED"}]}})
    monkeypatch.setattr(epmc.httpx, "AsyncClient", fake, raising=False)
    monkeypatch.setattr(epmc, "_RETRY_BACKOFF_SECONDS", 0.0)

    with pytest.raises(LiteratureSourceUnavailableError):
        await EuropePmcClient().search_or_raise("TITLE_ABS:test")


class TestMarkupStripping:
    """Europe PMC returns JATS markup inside titles and abstracts.

    It arrives in both forms -- raw `<i>` and escaped `&lt;i&gt;` -- and both
    reach the reader as literal angle brackets and the model as tokens to
    ignore.
    """

    def test_both_forms_of_markup_are_removed(self):
        assert strip_markup("<i>Mycobacterium tuberculosis</i> Pks13") == (
            "Mycobacterium tuberculosis Pks13"
        )
        assert strip_markup("&lt;i&gt;N&lt;/i&gt;-(Arylcarbamothioyl)benzamides") == (
            "N-(Arylcarbamothioyl)benzamides"
        )

    def test_block_boundaries_do_not_close_up(self):
        # Without a separator this reads "BackgroundTuberculosis", which is
        # worse than the tag was.
        assert strip_markup("<h4>Background</h4>Tuberculosis remains") == (
            "Background Tuberculosis remains"
        )

    def test_comparisons_survive_being_mistaken_for_tags(self):
        """The reason entities are unescaped last rather than first.

        Unescape first and `IC50 &gt; 100` becomes `IC50 > 100`, after which the
        tag pattern happily eats from a later `<` all the way to that `>` --
        deleting real text, silently, in exactly the potency figures this corpus
        exists to read.
        """
        assert strip_markup("MIC &gt; 100 uM and IC50 &lt; 0.5 uM") == (
            "MIC > 100 uM and IC50 < 0.5 uM"
        )
        assert strip_markup("hERG IC50 &lt;10 uM") == "hERG IC50 <10 uM"

    def test_subscripts_close_up_because_they_are_one_token(self):
        assert strip_markup("IC&lt;sub&gt;50&lt;/sub&gt; of 0.32") == "IC50 of 0.32"

    def test_empty_and_missing_stay_none(self):
        assert strip_markup(None) is None
        assert strip_markup("   ") is None
        assert strip_markup("<p></p>") is None

    def test_no_markup_survives_the_real_fixture(self, hits):
        for hit in hits.values():
            for field, value in (("title", hit.title), ("abstract", hit.abstract)):
                if not value:
                    continue
                assert "<" not in value or not re.search(r"<[a-zA-Z/]", value), (
                    f"{hit.external_id} {field} still has a tag: {value[:80]}"
                )
                assert "&lt;" not in value and "&gt;" not in value, (
                    f"{hit.external_id} {field} still has entities: {value[:80]}"
                )


RETRACTED_FIXTURE = FIXTURE.parent / "europe_pmc_retracted.json"


def _retracted_hit():
    record = json.loads(RETRACTED_FIXTURE.read_text())["resultList"]["result"][0]
    return parse_hit(record)


def test_retraction_is_parsed_from_a_core_record():
    hit = _retracted_hit()

    assert hit.is_retracted is True
    assert "Retracted Publication" in hit.pub_types
    assert hit.retraction_notice is not None
    assert "10.7759/cureus.r217" in hit.retraction_notice
    assert hit.cited_by_count == 3


def test_a_retracted_paper_is_never_ingestable_even_under_an_open_licence():
    """cc by, in EPMC, has a PDF — every existing gate says yes."""
    hit = _retracted_hit()

    assert hit.licence == "cc by"
    assert hit.in_epmc and hit.has_pdf
    assert hit.ingest_blocker() == "retracted publication"
    assert hit.is_ingestable is False


def test_an_ordinary_record_is_unaffected():
    records = json.loads(FIXTURE.read_text())["resultList"]["result"]
    hits = [parse_hit(r) for r in records]

    assert all(h.is_retracted is False for h in hits)
    assert any(h.is_ingestable for h in hits), "the open-licence fixture must still ingest"
