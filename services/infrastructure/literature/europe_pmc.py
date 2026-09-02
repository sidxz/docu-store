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
        if not (self.in_epmc and self.has_pdf):
            return "no full text available to fetch"
        return None

    @property
    def is_retracted(self) -> bool:
        return "retracted publication" in {p.lower() for p in self.pub_types}

    @property
    def is_ingestable(self) -> bool:
        return self.ingest_blocker() is None


# Europe PMC returns JATS markup inside titles and abstracts, in both forms:
# raw (`<i>Mycobacterium tuberculosis</i>`, `<h4>Background</h4>`) and escaped
# (`&lt;i&gt;N&lt;/i&gt;`). Both reach the reader as literal angle brackets, and
# both reach the model as tokens it has to ignore.
_BLOCK_CLOSE_RE = re.compile(r"(?:</|&lt;/)(?:p|div|sec|title|h[1-6]|li)\s*(?:>|&gt;)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[a-zA-Z/][^>]*>")
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


def parse_hit(record: dict) -> LiteratureHit:
    """One ``resultList.result`` entry to a LiteratureHit."""
    journal = (record.get("journalInfo") or {}).get("journal") or {}
    licence = record.get("license")
    year = record.get("pubYear")
    pub_types = tuple((record.get("pubTypeList") or {}).get("pubType") or ())
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
        query's fault and is not retried.
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
                    results = response.json()["resultList"]["result"]
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRYABLE_STATUS:
                    break
            except Exception as exc:  # timeouts, DNS, malformed JSON
                last_exc = exc
            else:
                return [parse_hit(r) for r in results]

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

        import httpx

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
