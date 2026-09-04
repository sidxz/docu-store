"""Europe PMC as a literature source: what is published, and what we may keep.

Search reaches 48.8M records — effectively all of biomedicine — but only 8.05M
carry a licence that lets us persist the full text. That gap is the whole shape
of this module: nearly every query returns papers we can show and cannot store.

**The licence is the gate, not ``isOpenAccess``.** Three real results from one
query make the point, and each breaks the obvious rule:

===============================  ==============  ==============  ==============
Record                           isOpenAccess    licence         Verdict
===============================  ==============  ==============  ==============
Research Square preprint         N               ``cc by``       ingestable
Biochemistry 2022                N (inEPMC=Y)    none            free to read,
                                                                 not to mine
ACS Omega 2025                   Y               ``cc by-nc-nd`` no derivatives
===============================  ==============  ==============  ==============

So ``isOpenAccess`` both under- and over-approximates. ``license`` decides, and
ND is excluded: chunking a paper and storing its embeddings is hard to argue is
not a derivative work, and the ~20% of the open corpus that ND costs us is not
worth the argument. ND papers still surface — they read as any other paper we
can link to but not keep.

Full text is fetched as **PDF, not JATS XML**, even though the XML is cleaner
and eight times smaller. CSER reads chemical structures off rendered page
images, which exist only in the PDF; ingesting XML would silently drop compound
extraction, which is most of why a paper is worth having here at all.

One subtlety for anyone measuring coverage with this: Europe PMC's default
search matches *full text* where it has it, and it only has full text for open
papers. A bare query therefore looks far more open-access than the literature
is. Restrict to ``TITLE_ABS:`` to compare like with like.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape

import httpx
import structlog

logger = structlog.get_logger()

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PDF_URL = "https://europepmc.org/articles/{pmcid}?pdf=render"
ARTICLE_URL = "https://europepmc.org/article/{source}/{external_id}"

_TIMEOUT_SECONDS = 30.0
_PDF_TIMEOUT_SECONDS = 120.0  # a rendered paper runs to a few MB
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 1.0
# EBI returns 502/503/504 in short bursts several times an hour. Measured
# 2026-09-02: a plain curl needed four attempts over ~6s to get a 200.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# Licences under which we may keep and chunk the full text. Everything else --
# ND variants, and the far larger set carrying no licence at all -- is link-only.
INGESTABLE_LICENCES = frozenset(
    {"cc by", "cc by-sa", "cc0", "cc by-nc", "cc by-nc-sa"},
)

# Both halves of a record's identity go into a query string, so both are checked
# before they get there. Sources are three uppercase letters (MED, PMC, PPR,
# PAT...); ids are bare alphanumerics (41591406, PMC12910649, PPR1298287).
_SOURCE_RE = re.compile(r"^[A-Z]{3}$")
_EXTERNAL_ID_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")


class LiteratureQueryError(Exception):
    """Europe PMC rejected the query itself.

    Kept apart from an outage because the advice is opposite: an outage should be
    retried unchanged, a rejected query must be rewritten before it is sent again.
    """


class LiteratureSourceUnavailableError(Exception):
    """Europe PMC could not be reached.

    Distinct from "no such record", and the distinction is not academic: their
    API returns 503 often enough that collapsing the two tells a user their
    paper does not exist when it does.
    """


@dataclass(frozen=True)
class LiteratureHit:
    """One Europe PMC record, in the terms this codebase cares about."""

    external_id: str
    source: str  # MED (PubMed) | PMC | PPR (preprint) | AGR | CBA ...
    title: str
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    abstract: str | None = None
    journal: str | None = None
    year: int | None = None
    authors: str | None = None
    licence: str | None = None
    is_open_access: bool = False  # for display only -- never the ingest gate
    in_epmc: bool = False
    has_pdf: bool = False
    pub_types: tuple[str, ...] = ()
    retraction_notice: str | None = None  # the notice's own citation, when retracted
    cited_by_count: int = 0

    @property
    def url(self) -> str:
        """Where a reader should be sent — the publisher's copy when we know it."""
        if self.doi:
            return f"https://doi.org/{self.doi}"
        return ARTICLE_URL.format(source=self.source, external_id=self.external_id)

    def ingest_blocker(self) -> str | None:
        """Why this may not be ingested, or None when it may.

        Returned rather than a bare bool so the UI can say which of the two very
        different reasons applies: we are not allowed to keep it, or there is
        nothing to fetch.
        """
        if self.is_retracted:
            return "retracted publication"
        if self.licence not in INGESTABLE_LICENCES:
            if self.licence:
                return f"licence {self.licence} does not permit derivative works"
            return "no open licence — abstract and link only"
        # pmcid included: fetch_pdf formats it into the URL, and without it the
        # UI offers an Add button that resolves to .../articles/None.
        if not (self.in_epmc and self.has_pdf and self.pmcid):
            return "no full text available to fetch"
        return None

    @property
    def is_retracted(self) -> bool:
        return "retracted publication" in {p.lower() for p in self.pub_types}

    @property
    def is_ingestable(self) -> bool:
        return self.ingest_blocker() is None


# Above this many matches, one request cannot return every record. Europe PMC
# caps pageSize at 1000 and orders by relevance, which correlates hard with
# recency -- so the first page of a large result set is NOT a sample of the
# field, and histogramming it reports that the field began this year.
_EXHAUSTIVE_LIMIT = 1000


@dataclass(frozen=True)
class YearCounts:
    """Publication counts per year for a whole query, not for a fetched page."""

    query: str
    total: int
    counts: dict[int, int]
    records: list[LiteratureHit]
    exhaustive: bool
    """True when ``records`` holds every match, so other panels are free."""


# Europe PMC returns JATS markup inside titles and abstracts, in both forms:
# raw (`<i>Mycobacterium tuberculosis</i>`, `<h4>Background</h4>`) and escaped
# (`&lt;i&gt;N&lt;/i&gt;`). Both reach the reader as literal angle brackets, and
# both reach the model as tokens it has to ignore.
_BLOCK_CLOSE_RE = re.compile(r"(?:</|&lt;/)(?:p|div|sec|title|h[1-6]|li)\s*(?:>|&gt;)", re.IGNORECASE)
# A tag is a name followed immediately by `>`, or by attributes containing `=`.
# Without that second half `MIC <LOD in the resistant strain and IC50 > 5 uM`
# reads as one tag and everything between the brackets is deleted -- the same
# failure _ESCAPED_TAG_RE is bounded against, on the raw path.
_TAG_RE = re.compile(
    r"</?[a-zA-Z][a-zA-Z0-9-]{0,19}"
    r"(?:\s+[a-zA-Z-]+=(?:\"[^\"]*\"|'[^']*'))*"
    r"\s*/?>",
)
# Escaped tags only: a tag name must follow the bracket. `&lt; 0.5` and
# `&lt;10 uM` are comparisons, not markup, and must survive to be unescaped
# into the operators they are.
_ESCAPED_TAG_RE = re.compile(r"&lt;/?[a-zA-Z][^&]{0,40}?&gt;")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_markup(value: str | None) -> str | None:
    """Plain text from a JATS-marked field.

    Order matters. Tags are removed while they are still recognisable as tags,
    and entities are unescaped only afterwards -- unescaping first would turn
    `IC50 &gt; 100` into `IC50 > 100` and then let the tag pattern eat from the
    `<` of a later comparison to that `>`, silently deleting real text.
    """
    if not value:
        return None
    # Block boundaries carry meaning: without this, "<h4>Background</h4>Tuberculosis"
    # closes up into "BackgroundTuberculosis".
    text = _BLOCK_CLOSE_RE.sub(" ", value)
    text = _TAG_RE.sub("", text)
    text = _ESCAPED_TAG_RE.sub("", text)
    text = unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip() or None


def _flag(value: object) -> bool:
    """Europe PMC spells its booleans ``"Y"``/``"N"``."""
    return str(value).strip().upper() == "Y"


def _pub_types(record: dict) -> tuple[str, ...]:
    """Publication types, from either result shape.

    ``resultType=core`` sends ``pubTypeList.pubType`` as a list;
    ``resultType=lite`` -- what year_counts uses -- sends ``pubTypeList: null``
    and a flat semicolon-joined ``pubType`` string instead. Reading only the
    core shape left every lite record with no types at all, which silently
    bucketed reviews and preprints as research articles and disarmed the
    retraction check on the counting path.
    """
    listed = (record.get("pubTypeList") or {}).get("pubType")
    if listed:
        return tuple(listed)
    flat = record.get("pubType")
    if isinstance(flat, str):
        return tuple(p.strip() for p in flat.split(";") if p.strip())
    return ()


def parse_hit(record: dict) -> LiteratureHit:
    """One ``resultList.result`` entry to a LiteratureHit."""
    journal = (record.get("journalInfo") or {}).get("journal") or {}
    licence = record.get("license")
    year = record.get("pubYear")
    pub_types = _pub_types(record)
    corrections = (record.get("commentCorrectionList") or {}).get("commentCorrection") or []
    retraction_notice = next(
        (
            c.get("reference")
            for c in corrections
            if str(c.get("type", "")).lower().startswith("retraction")
        ),
        None,
    )
    cited_by = record.get("citedByCount")
    return LiteratureHit(
        external_id=str(record["id"]),
        source=str(record.get("source") or ""),
        title=strip_markup(record.get("title")) or "",
        doi=record.get("doi"),
        pmid=record.get("pmid"),
        pmcid=record.get("pmcid"),
        abstract=strip_markup(record.get("abstractText")),
        journal=strip_markup(journal.get("title")),
        year=int(year) if year and str(year).isdigit() else None,
        authors=record.get("authorString"),
        licence=licence.strip().lower() if licence else None,
        is_open_access=_flag(record.get("isOpenAccess")),
        in_epmc=_flag(record.get("inEPMC")),
        has_pdf=_flag(record.get("hasPDF")),
        pub_types=pub_types,
        retraction_notice=retraction_notice,
        cited_by_count=int(cited_by) if isinstance(cited_by, int) else 0,
    )


def hit_payload(hit: LiteratureHit) -> dict:
    """The wire form of a hit — the REST search and the chat SSE event send this.

    One function rather than two hand-written dicts: they had already drifted,
    and the REST copy was three fields short of the type the client declares.
    """
    return {
        "external_id": hit.external_id,
        "source": hit.source,
        "title": hit.title,
        "doi": hit.doi,
        "pmid": hit.pmid,
        "pmcid": hit.pmcid,
        "abstract": hit.abstract,
        "journal": hit.journal,
        "year": hit.year,
        "authors": hit.authors,
        "licence": hit.licence,
        "is_open_access": hit.is_open_access,
        "url": hit.url,
        "is_ingestable": hit.is_ingestable,
        "ingest_blocker": hit.ingest_blocker(),
        "is_retracted": hit.is_retracted,
        "retraction_notice": hit.retraction_notice,
        "cited_by_count": hit.cited_by_count,
    }


class EuropePmcClient:
    """Read-only client for Europe PMC's public REST API. No key required."""

    def __init__(self, search_url: str = SEARCH_URL) -> None:
        self._search_url = search_url

    async def search(self, query: str, *, limit: int = 25) -> list[LiteratureHit]:
        """Records matching ``query``, or an empty list if Europe PMC is down.

        Failure is empty rather than raised: a literature search that cannot
        reach its source should leave the chat saying so, not error the turn.
        Callers that must tell "nothing found" from "nothing reachable" -- ingest
        -- use :meth:`search_or_raise` instead.
        """
        try:
            return await self.search_or_raise(query, limit=limit)
        except LiteratureSourceUnavailableError:
            logger.warning("europe_pmc_search_failed", query=query, exc_info=True)
            return []

    async def search_or_raise(self, query: str, *, limit: int = 25) -> list[LiteratureHit]:
        """As :meth:`search`, but an unreachable source raises.

        Transient 5xx is retried: EBI drops requests in short bursts, and a
        single-shot client turns that into a silently thin answer. A 4xx is the
        query's fault, so it is not retried and raises LiteratureQueryError --
        reporting it as an outage tells the caller to send it again unchanged.
        """
        params = {
            "query": query,
            "format": "json",
            "resultType": "core",  # the only resultType carrying licence + abstract
            "pageSize": str(min(limit, 100)),
        }
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                    response = await client.get(self._search_url, params=params)
                    response.raise_for_status()
                    # Parsed inside the try: a record missing `id` is a malformed
                    # response, and raising KeyError from the else clause takes it
                    # past every caller's handler and out as a bare 500.
                    hits = [parse_hit(r) for r in response.json()["resultList"]["result"]]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _RETRYABLE_STATUS:
                    msg = f"Europe PMC rejected the query ({exc.response.status_code}): {query}"
                    raise LiteratureQueryError(msg) from exc
                last_exc = exc
            except Exception as exc:  # timeouts, DNS, malformed JSON
                last_exc = exc
            else:
                return hits

            if attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))

        msg = f"Europe PMC is unreachable: {last_exc}"
        raise LiteratureSourceUnavailableError(msg) from last_exc

    async def fetch_one(self, source: str, external_id: str) -> LiteratureHit | None:
        """One record by its Europe PMC identity, or None if there is no such record.

        Ingest re-fetches through here rather than trusting the hit the browser
        sends back: a licence gate the caller supplies the input to is not a gate.
        """
        if not _SOURCE_RE.match(source) or not _EXTERNAL_ID_RE.match(external_id):
            logger.warning(
                "europe_pmc_bad_identity",
                source=source[:16],
                external_id=external_id[:32],
            )
            return None
        hits = await self.search_or_raise(f"EXT_ID:{external_id} AND SRC:{source}", limit=1)
        return hits[0] if hits else None

    async def fetch_pdf(self, hit: LiteratureHit) -> bytes | None:
        """The rendered PDF, or None when it cannot be had.

        Refuses on licence before touching the network — a caller that has not
        checked ``is_ingestable`` must not be able to pull bytes we may not keep.
        """
        blocker = hit.ingest_blocker()
        if blocker is not None:
            logger.info(
                "europe_pmc_fetch_refused",
                external_id=hit.external_id,
                licence=hit.licence,
                reason=blocker,
            )
            return None

        url = PDF_URL.format(pmcid=hit.pmcid)
        try:
            async with httpx.AsyncClient(
                timeout=_PDF_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                body = response.content
        except Exception:
            logger.warning(
                "europe_pmc_pdf_failed",
                external_id=hit.external_id,
                pmcid=hit.pmcid,
                exc_info=True,
            )
            return None

        # Europe PMC answers 200 with an HTML error page when a render fails,
        # so trust the magic bytes rather than the status.
        if not body.startswith(b"%PDF"):
            logger.warning(
                "europe_pmc_pdf_not_a_pdf",
                external_id=hit.external_id,
                pmcid=hit.pmcid,
                head=body[:32],
            )
            return None
        return body

    async def year_counts(self, query: str, *, since: int = 1990) -> YearCounts:
        """Papers per year across the whole match, in two regimes.

        Under ``_EXHAUSTIVE_LIMIT`` matches one request returns every record, so
        the caller also gets citations and publication types for free. Above it,
        one count-only request per year -- exact, tiny, and all that is available
        without paging the whole set.

        ``query`` is sent unchanged. A broadened counting query would describe a
        different population than the cards the same search produced.
        """
        first = await self._raw_search(query, page_size=_EXHAUSTIVE_LIMIT)
        total = int(first.get("hitCount") or 0)
        # A 200 whose body is not the shape we expect is an outage, not a bug in
        # the caller: raising KeyError here goes past every caller's handler and
        # out as a bare 500 on a panel that was meant to be refusable.
        try:
            records = [parse_hit(r) for r in first["resultList"]["result"]]
        except (KeyError, TypeError, ValueError) as exc:
            msg = f"Europe PMC returned an unexpected body: {exc}"
            raise LiteratureSourceUnavailableError(msg) from exc

        if total <= _EXHAUSTIVE_LIMIT:
            counts: dict[int, int] = {}
            for hit in records:
                if hit.year is not None:
                    counts[hit.year] = counts.get(hit.year, 0) + 1
            return YearCounts(
                query=query,
                total=total,
                counts=counts,
                records=records,
                exhaustive=True,
            )

        this_year = datetime.now(UTC).year
        years = list(range(since, this_year + 1))
        payloads = await asyncio.gather(
            *(
                self._raw_search(f"({query}) AND PUB_YEAR:{y}", page_size=1)
                for y in years
            ),
        )
        return YearCounts(
            query=query,
            total=total,
            counts={
                y: int(p.get("hitCount") or 0)
                for y, p in zip(years, payloads, strict=True)
                if int(p.get("hitCount") or 0) > 0
            },
            records=[],
            exhaustive=False,
        )

    async def _raw_search(self, query: str, *, page_size: int) -> dict:
        """One search request, retried on transient 5xx, returning parsed JSON.

        ``resultType=lite`` rather than ``core``: it carries pubYear, pubType,
        citedByCount, isOpenAccess and journalTitle -- everything the panels
        need -- at roughly a tenth the bytes of core, which matters at 1000
        records.
        """
        params = {
            "query": query,
            "format": "json",
            "resultType": "lite",
            "pageSize": str(page_size),
        }
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                    response = await client.get(self._search_url, params=params)
                    response.raise_for_status()
                    body = response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _RETRYABLE_STATUS:
                    msg = f"Europe PMC rejected the query ({exc.response.status_code}): {query}"
                    raise LiteratureQueryError(msg) from exc
                last_exc = exc
            except Exception as exc:
                last_exc = exc
            else:
                return body

            if attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))

        msg = f"Europe PMC is unreachable: {last_exc}"
        raise LiteratureSourceUnavailableError(msg) from last_exc
