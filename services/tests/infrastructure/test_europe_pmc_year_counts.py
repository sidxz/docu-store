"""Counting a whole result set, rather than the page retrieval happened to fetch.

Two regimes, and the boundary between them is the only interesting thing here:
under a thousand matches one request returns every record, so the counts come
with citations and publication types attached. Over a thousand, only the counts
survive.
"""

from __future__ import annotations

import json

import httpx
import pytest

from infrastructure.literature import europe_pmc as epmc
from infrastructure.literature.europe_pmc import EuropePmcClient


def _payload(hit_count: int, years: list[int]) -> str:
    return json.dumps(
        {
            "hitCount": hit_count,
            "resultList": {
                "result": [
                    {
                        "id": str(1000 + i),
                        "source": "MED",
                        "title": f"Paper {i}",
                        "pubYear": str(y),
                        "pubType": "research-article",
                        "citedByCount": i,
                    }
                    for i, y in enumerate(years)
                ],
            },
        },
    )


class _FakeAsyncClient:
    """Replaces httpx.AsyncClient; yields one queued response per GET."""

    def __init__(self, bodies: list[str]) -> None:
        self._bodies = list(bodies)
        self.requests: list[dict] = []

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None, **kwargs):
        self.requests.append(dict(params or {}))
        body = self._bodies.pop(0)
        return httpx.Response(
            200,
            text=body,
            request=httpx.Request("GET", url),
        )


async def test_small_result_set_is_counted_from_one_request(monkeypatch):
    fake = _FakeAsyncClient([_payload(4, [2019, 2020, 2020, 2024])])
    monkeypatch.setattr(epmc.httpx, "AsyncClient", fake, raising=False)

    result = await EuropePmcClient().year_counts('TITLE_ABS:"MmpL3"')

    assert len(fake.requests) == 1
    assert result.total == 4
    assert result.counts == {2019: 1, 2020: 2, 2024: 1}
    assert result.exhaustive is True
    # The records come back too, so the evidence-mix and landmark panels are
    # free once this call has been made.
    assert len(result.records) == 4
    assert result.records[0].cited_by_count == 0
    # ``resultType=lite`` carries pubType as a flat string with pubTypeList
    # null. Reading only the core shape left pub_types empty for every record,
    # and bucket_pub_type then called all of them research articles.
    assert result.records[0].pub_types == ("research-article",)


async def test_the_counting_query_is_sent_unchanged(monkeypatch):
    # If this broadens, the chart describes a different population than the
    # cards beneath it and nothing on screen reveals the disagreement.
    query = 'TITLE_ABS:"Pks13" AND TITLE_ABS:"inhibitor"'
    fake = _FakeAsyncClient([_payload(1, [2023])])
    monkeypatch.setattr(epmc.httpx, "AsyncClient", fake, raising=False)

    await EuropePmcClient().year_counts(query)

    assert fake.requests[0]["query"] == query


async def test_large_result_set_falls_back_to_per_year_counts(monkeypatch):
    # 15,158 matches whose first page is almost entirely the current year is the
    # real measured case; histogramming that page reports the field began now.
    probe = _payload(15158, [2026])
    # One request per year from `since` through NEXT year: Europe PMC dates a
    # paper by its journal issue, which runs ahead of the calendar.
    per_year = [_payload(n, []) for n in (10, 20, 30, 40)]
    fake = _FakeAsyncClient([probe, *per_year])
    monkeypatch.setattr(epmc.httpx, "AsyncClient", fake, raising=False)

    result = await EuropePmcClient().year_counts(
        'TITLE_ABS:"machine learning"', since=2024,
    )

    assert result.total == 15158
    assert result.exhaustive is False
    assert result.records == []
    assert result.counts == {2024: 10, 2025: 20, 2026: 30, 2027: 40}
    assert 'PUB_YEAR:2024' in fake.requests[1]["query"]


async def test_per_year_false_returns_the_total_without_the_fan_out(monkeypatch):
    # Only the timeline can spend the per-year sweep; every other panel draws
    # its own series and needs the total alone. Firing 38 requests a facet to
    # build counts nobody reads was most of this feature's Europe PMC traffic.
    fake = _FakeAsyncClient([_payload(15158, [2026])])
    monkeypatch.setattr(epmc.httpx, "AsyncClient", fake, raising=False)

    result = await EuropePmcClient().year_counts('TITLE_ABS:"x"', per_year=False)

    assert len(fake.requests) == 1
    assert result.total == 15158
    assert result.counts == {}
    assert result.exhaustive is False


async def test_top_cited_asks_europe_pmc_to_do_the_sorting(monkeypatch):
    # One request at any match size, which is why landmarks no longer needs an
    # exhaustive fetch — and why it stopped forcing the model into queries
    # narrow enough to exclude the canonical papers it exists to surface.
    fake = _FakeAsyncClient([_payload(31706, [2001, 2017])])
    monkeypatch.setattr(epmc.httpx, "AsyncClient", fake, raising=False)

    hits = await EuropePmcClient().top_cited('TITLE_ABS:"metformin"', limit=40)

    assert len(fake.requests) == 1
    assert fake.requests[0]["sort"] == "CITED desc"
    assert fake.requests[0]["pageSize"] == "40"
    assert [h.year for h in hits] == [2001, 2017]


async def test_an_outage_raises_rather_than_returning_empty_counts(monkeypatch):
    class _Failing(_FakeAsyncClient):
        async def get(self, url, params=None, **kwargs):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(epmc.httpx, "AsyncClient", _Failing([]), raising=False)
    monkeypatch.setattr(epmc, "_RETRY_BACKOFF_SECONDS", 0.0)

    with pytest.raises(epmc.LiteratureSourceUnavailableError):
        await EuropePmcClient().year_counts('TITLE_ABS:"MmpL3"')


async def test_a_malformed_200_body_is_an_outage_not_a_key_error(monkeypatch):
    # Europe PMC answers 200 with a body missing resultList often enough to
    # matter. Letting the KeyError out takes it past every caller's handler and
    # surfaces as a bare 500 on a chart nobody asked to be fatal.
    fake = _FakeAsyncClient([json.dumps({"hitCount": 3})])
    monkeypatch.setattr(epmc.httpx, "AsyncClient", fake, raising=False)

    with pytest.raises(epmc.LiteratureSourceUnavailableError):
        await EuropePmcClient().year_counts('TITLE_ABS:"MmpL3"')


async def test_a_record_that_cannot_be_parsed_is_an_outage_too(monkeypatch):
    body = json.dumps({"hitCount": 1, "resultList": {"result": [{"source": "MED"}]}})
    fake = _FakeAsyncClient([body])
    monkeypatch.setattr(epmc.httpx, "AsyncClient", fake, raising=False)

    with pytest.raises(epmc.LiteratureSourceUnavailableError):
        await EuropePmcClient().year_counts('TITLE_ABS:"MmpL3"')
