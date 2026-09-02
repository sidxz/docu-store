"""Searching external literature, and taking a copy of what we are allowed to keep.

Ingest deliberately re-fetches the record it is asked about. The caller sends an
identity — source and id — and nothing else: every fact the decision turns on,
above all the licence, is read from Europe PMC on the server. A gate whose input
comes from the browser is not a gate.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result

from application.dtos.blob_dtos import UploadBlobRequest
from application.dtos.errors import AppError
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.source_class import SourceClass
from infrastructure.literature.europe_pmc import (
    LiteratureQueryError,
    LiteratureSourceUnavailableError,
)

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.artifact_dtos import ArtifactResponse
    from application.ports.auth import AuthContext
    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.sagas.artifact_upload_saga import ArtifactUploadSaga
    from infrastructure.literature.europe_pmc import EuropePmcClient, LiteratureHit

log = structlog.get_logger(__name__)


class SearchLiteratureUseCase:
    """Query Europe PMC. Read-only, and touches nothing in this workspace."""

    def __init__(self, client: EuropePmcClient) -> None:
        self._client = client

    async def execute(self, query: str, *, limit: int = 25) -> list[LiteratureHit]:
        return await self._client.search(query, limit=limit)


class IngestLiteratureUseCase:
    """Fetch one open-licensed paper and put it through the normal upload path.

    Nothing here is bespoke past the fetch: the paper reaches the saga as a
    stream and a filename, exactly as a browser upload would, and everything
    downstream — parse, NER, CSER, embeddings, summaries — happens because
    Artifact.Created fired, not because this use case asked for it.
    """

    def __init__(
        self,
        client: EuropePmcClient,
        upload_saga: ArtifactUploadSaga,
        artifact_read_model: ArtifactReadModel,
    ) -> None:
        self._client = client
        self._saga = upload_saga
        self._artifacts = artifact_read_model

    async def execute(
        self,
        *,
        source: str,
        external_id: str,
        visibility: str = "private",
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        try:
            hit = await self._client.fetch_one(source, external_id)
        except (LiteratureSourceUnavailableError, LiteratureQueryError):
            # Not "no such paper" -- saying that would be a lie the user cannot
            # check, and Europe PMC 503s often enough for it to matter.
            log.warning("literature.source_unavailable", external_id=external_id, exc_info=True)
            return Failure(
                AppError("infrastructure", "Europe PMC is unavailable right now — try again"),
            )
        if hit is None:
            return Failure(
                AppError("not_found", f"No Europe PMC record {source}/{external_id}"),
            )

        blocker = hit.ingest_blocker()
        if blocker is not None:
            # 403 rather than 400: the request is well formed and the paper is
            # real. We are simply not permitted to keep this one.
            return Failure(
                AppError("forbidden", f"Cannot ingest {hit.external_id}: {blocker}"),
            )

        workspace_id: UUID | None = auth.workspace_id if auth else None
        existing = await self._artifacts.find_artifact_id_by_source_uri(hit.url, workspace_id)
        if existing is not None:
            # Not an error. The caller asked for this paper to be in the library
            # and it is, so say where rather than spending a fetch and a parse
            # on a second copy.
            return Failure(
                AppError("conflict", f"Already in this workspace as {existing}"),
            )

        pdf = await self._client.fetch_pdf(hit)
        if pdf is None:
            return Failure(
                AppError(
                    "infrastructure",
                    f"Europe PMC did not return a PDF for {hit.external_id}",
                ),
            )

        log.info(
            "literature.ingesting",
            external_id=hit.external_id,
            licence=hit.licence,
            size_bytes=len(pdf),
            visibility=visibility,
        )

        return await self._saga.execute(
            stream=BytesIO(pdf),
            upload_req=UploadBlobRequest(
                source_uri=hit.url,
                artifact_type=ArtifactType.RESEARCH_ARTICLE,
                filename=_filename_for(hit),
                mime_type="application/pdf",
                visibility=visibility,
                source_class=SourceClass.LITERATURE_OA,
                licence=hit.licence,
            ),
            auth=auth,
        )


def _filename_for(hit: LiteratureHit) -> str:
    """A name a human can recognise in a document list, not an opaque id."""
    stem = hit.pmcid or f"{hit.source}{hit.external_id}"
    return f"{stem}.pdf"
