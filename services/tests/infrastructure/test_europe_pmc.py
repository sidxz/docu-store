"""Parsing Europe PMC, and deciding what may be kept from it.

The fixture is ten real records from one query (`InhA` + `inhibitor`), kept
because three of them break the rule anyone would write first. `isOpenAccess`
is not the ingest gate; the licence is.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.literature.europe_pmc import (
    EuropePmcClient,
    LiteratureHit,
    parse_hit,
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


async def test_search_returns_empty_when_europe_pmc_is_unreachable():
    # Their API 503'd twice while this was being written. A dead source should
    # leave the chat able to say so, not error the turn.
    client = EuropePmcClient(search_url="http://127.0.0.1:9/search")
    assert await client.search("InhA") == []
