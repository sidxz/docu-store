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
from infrastructure.literature.europe_pmc import LiteratureQueryError, hit_payload
from interfaces.api.middleware import handle_use_case_errors
from interfaces.api.routes.helpers import (
    ensure_llm_configured,
    ensure_terms_accepted,
    ensure_within_quota,
    require_action,
    require_literature_enabled,
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
    is_retracted: bool = False
    retraction_notice: str | None = None
    cited_by_count: int = 0


class IngestLiteratureRequest(BaseModel):
    """Identity only. Everything the decision turns on is re-read server-side."""

    source: str = Field(..., description="Europe PMC source, e.g. MED, PMC, PPR")
    external_id: str = Field(..., description="Europe PMC record id")
    visibility: str = Field(
        "private",
        pattern=r"^(private|workspace)$",
        description="Private to the requester, or shared with the workspace",
    )


# No @handle_use_case_errors: that decorator unwraps a returns.Result, and a
# plain list falls through it into a 500 on every call.
@router.get("/search", status_code=status.HTTP_200_OK)
async def search_literature(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],  # noqa: ARG001 — authenticates the caller; search reads nothing owned by them
    q: Annotated[str, Query(min_length=2, max_length=500, description="Europe PMC query")],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[LiteratureHitResponse]:
    """Search Europe PMC. Reads nothing from this workspace and writes nothing."""
    require_literature_enabled()
    use_case = container[SearchLiteratureUseCase]
    try:
        hits = await use_case.execute(q, limit=limit)
    except LiteratureQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return [LiteratureHitResponse(**hit_payload(h)) for h in hits]


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
    require_literature_enabled()
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
