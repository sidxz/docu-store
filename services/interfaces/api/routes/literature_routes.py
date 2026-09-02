"""External literature search and open-access ingest.

Both routes 404 when LITERATURE_ENABLED is off, rather than 403: a deployment
that has not turned this on should look like one that never had it, so the flag
is a deployment decision and not a permission the UI can ask about.
"""

from typing import Annotated

from duar_auth import RequestAuth
from fastapi import APIRouter, Depends, HTTPException, Query, status
from lagom import Container
from pydantic import BaseModel, Field

from application.dtos.artifact_dtos import ArtifactResponse
from application.use_cases.literature_use_cases import (
    IngestLiteratureUseCase,
    SearchLiteratureUseCase,
)
from infrastructure.config import settings
from interfaces.api.middleware import handle_use_case_errors
from interfaces.api.routes.helpers import (
    ensure_llm_configured,
    ensure_terms_accepted,
    ensure_within_quota,
    require_action,
)
from interfaces.dependencies import get_auth, get_container

router = APIRouter(prefix="/literature", tags=["literature"])


class LiteratureHitResponse(BaseModel):
    """One search result, carrying its own verdict on whether it may be kept."""

    external_id: str
    source: str
    title: str
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    abstract: str | None = None
    journal: str | None = None
    year: int | None = None
    authors: str | None = None
    licence: str | None = None
    is_open_access: bool = False
    url: str
    is_ingestable: bool = Field(
        ...,
        description="Whether this workspace may take a copy. Decided from the licence.",
    )
    ingest_blocker: str | None = Field(
        None,
        description="Why not, in words meant for a reader. None when ingestable.",
    )


class IngestLiteratureRequest(BaseModel):
    """Identity only. Everything the decision turns on is re-read server-side."""

    source: str = Field(..., description="Europe PMC source, e.g. MED, PMC, PPR")
    external_id: str = Field(..., description="Europe PMC record id")
    visibility: str = Field(
        "private",
        pattern=r"^(private|workspace)$",
        description="Private to the requester, or shared with the workspace",
    )


def _require_enabled() -> None:
    if not settings.literature_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Literature search is not enabled on this deployment",
        )


@router.get("/search", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def search_literature(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],  # noqa: ARG001 — authenticates the caller; search reads nothing owned by them
    q: Annotated[str, Query(min_length=2, max_length=500, description="Europe PMC query")],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[LiteratureHitResponse]:
    """Search Europe PMC. Reads nothing from this workspace and writes nothing."""
    _require_enabled()
    use_case = container[SearchLiteratureUseCase]
    hits = await use_case.execute(q, limit=limit)
    return [
        LiteratureHitResponse(
            external_id=h.external_id,
            source=h.source,
            title=h.title,
            doi=h.doi,
            pmid=h.pmid,
            pmcid=h.pmcid,
            abstract=h.abstract,
            journal=h.journal,
            year=h.year,
            authors=h.authors,
            licence=h.licence,
            is_open_access=h.is_open_access,
            url=h.url,
            is_ingestable=h.is_ingestable,
            ingest_blocker=h.ingest_blocker(),
        )
        for h in hits
    ]


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
@handle_use_case_errors
async def ingest_literature(
    request: IngestLiteratureRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ArtifactResponse:
    """Fetch one open-licensed paper into the corpus.

    Gated exactly as an upload is -- it produces the same artifact and spends the
    same parse, NER, CSER and embedding budget, so it answers to the same quota.

    Returns:
        201 Created: ingested, parse running
        403 Forbidden: the licence does not permit keeping it
        404 Not Found: no such record, or the feature is off
        409 Conflict: already in this workspace

    """
    _require_enabled()
    await require_action(auth, "artifacts:create")
    await ensure_terms_accepted(auth, container)
    await ensure_llm_configured(auth, container)
    await ensure_within_quota(auth, container)
    use_case = container[IngestLiteratureUseCase]
    return await use_case.execute(
        source=request.source,
        external_id=request.external_id,
        visibility=request.visibility,
        auth=auth,
    )
