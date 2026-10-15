"""Workspace routes — Duar member/group proxies + admin token-limit config."""

import asyncio
from datetime import UTC, datetime
from io import BytesIO
from typing import Annotated
from uuid import UUID

from duar_auth import RequestAuth
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from lagom import Container
from pydantic import BaseModel, Field

from application.dtos.usage_dtos import TokenLimitEntry
from application.ports.blob_store import BlobStore
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.page_read_models import PageReadModel
from application.ports.token_limit_store import TokenLimitStore
from application.use_cases.cser_export_use_case import build_cser_export_zip
from interfaces.api.routes.helpers import get_allowed_artifact_ids, require_action
from interfaces.dependencies import get_auth, get_container

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/members", status_code=200)
async def search_members(
    auth: Annotated[RequestAuth, Depends(get_auth)],
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[dict]:
    """Search workspace members by name or email.

    Proxies to Duar's workspace member list endpoint.
    """
    return await auth.search_members(query=q, limit=limit)


@router.get("/groups", status_code=200)
async def list_groups(
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> list[dict]:
    """List groups in the current workspace."""
    return await auth.list_groups()


# ── Token limits (admin) ────────────────────────────────────────────────────


class TokenLimitBody(BaseModel):
    # Required (no default) so PUT {} or a typoed key 422s instead of silently
    # meaning "unlimited"; explicit null is still how you say unlimited.
    # le = Mongo's int64 ceiling — larger values crash BSON encoding with a 500.
    limit: int | None = Field(ge=0, le=2**63 - 1)


class WorkspaceTokenLimitsResponse(BaseModel):
    default_limit: int | None
    overrides: list[TokenLimitEntry]


def _require_admin(auth: RequestAuth) -> None:
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("/token-limits", status_code=status.HTTP_200_OK)
async def get_token_limits(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> WorkspaceTokenLimitsResponse:
    """Workspace-default + per-user monthly token limits (admin only)."""
    _require_admin(auth)
    rows = await container[TokenLimitStore].list_for_workspace(auth.workspace_id)
    default = next((r for r in rows if r.user_id is None), None)
    return WorkspaceTokenLimitsResponse(
        default_limit=default.limit if default else None,
        overrides=[r for r in rows if r.user_id is not None],
    )


# NOTE: /default must be declared before /{user_id} — otherwise "default"
# matches the UUID path param and 422s instead of reaching this route.
@router.put("/token-limits/default", status_code=status.HTTP_204_NO_CONTENT)
async def set_default_token_limit(
    body: TokenLimitBody,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Set the workspace-default monthly token limit (admin only). null = unlimited."""
    _require_admin(auth)
    await container[TokenLimitStore].set(
        auth.workspace_id, None, body.limit, updated_by=auth.user_id,
    )


@router.put("/token-limits/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def set_user_token_limit(
    user_id: UUID,
    body: TokenLimitBody,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Set a per-user monthly token limit override (admin only). null = unlimited."""
    _require_admin(auth)
    await container[TokenLimitStore].set(
        auth.workspace_id, user_id, body.limit, updated_by=auth.user_id,
    )


@router.delete("/token-limits/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_token_limit(
    user_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Remove a per-user override so the user falls back to the workspace default."""
    _require_admin(auth)
    await container[TokenLimitStore].delete(auth.workspace_id, user_id)


# ── CSER training export ────────────────────────────────────────────────────


async def _source_filenames_by_artifact_id(
    pages: list[dict], auth: RequestAuth, container: Container
) -> dict[str, str | None]:
    """Look up each distinct page artifact's `source_filename`.

    Pages don't carry the filename themselves; the artifact document does.
    """
    # sorted() because the set is iterated twice below and zipped positionally;
    # set iteration order is stable in practice but nothing guarantees it.
    artifact_ids = sorted({page["artifact_id"] for page in pages})
    repo = container[ArtifactReadModel]
    artifacts = await asyncio.gather(
        *(repo.get_artifact_by_id(UUID(artifact_id), workspace_id=auth.workspace_id) for artifact_id in artifact_ids)
    )
    return {
        artifact_id: artifact.source_filename if artifact else None
        for artifact_id, artifact in zip(artifact_ids, artifacts, strict=True)
    }


@router.get("/cser-training-export")
async def export_cser_training_data(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    only_reviewed: Annotated[bool, Query(description="Human-reviewed pages only")] = True,
    since: Annotated[datetime | None, Query(description="Only corrections at or after this time")] = None,
) -> StreamingResponse:
    """Download this workspace's CSER annotations as a structflo-cser data_dir.

    Unzips into images/ + ground_truth/ + labels/, ready for
    `sf-train-relmatch --data-dir <dir>` and for YOLO detector training.

    Defaults to human-reviewed pages only. `only_reviewed=false` adds machine
    output for bootstrapping — useful, but explicitly not ground truth.
    """
    await require_action(auth, "artifacts:hiledit")
    # hiledit says "may review annotations", not "may see every document": filter
    # to the artifacts this caller can actually view, like every other
    # multi-artifact endpoint does.
    allowed_artifact_ids = await get_allowed_artifact_ids(auth)

    read_model = container[PageReadModel]
    pages = await read_model.get_pages_for_cser_export(
        auth.workspace_id,
        only_reviewed=only_reviewed,
        since=since,
        allowed_artifact_ids=allowed_artifact_ids,
    )
    artifact_filenames = await _source_filenames_by_artifact_id(pages, auth, container)
    payload = build_cser_export_zip(
        pages, container[BlobStore], auth.workspace_id, datetime.now(UTC), artifact_filenames
    )
    filename = f"cser-training-{auth.workspace_id}.zip"
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Embedding model (self-serve) ────────────────────────────────────────────


class EmbeddingModelOption(BaseModel):
    id: str
    label: str
    providers: list[str]  # BYO-LLM provider ids whose key can serve it


class WorkspaceEmbeddingResponse(BaseModel):
    enabled: bool  # per-workspace models exist only in self-serve
    model: str  # "local" or an option id
    server_model: str  # what "local" runs
    has_documents: bool  # changing the model then re-embeds every document
    usable: bool  # the caller holds a key that can serve ``model``
    detail: str | None = None  # why not, when not
    options: list[EmbeddingModelOption]


class WorkspaceEmbeddingBody(BaseModel):
    model: str
    # Required to change the model of a workspace that already has documents:
    # every one of them is re-embedded (with its uploader's key).
    reembed: bool = False


class WorkspaceEmbeddingUpdate(BaseModel):
    model: str
    reembed_workflows: int


async def _current_embedding_model(container: Container, workspace_id: UUID) -> str:
    from application.ports.workspace_embedding_config import WorkspaceEmbeddingConfigStore
    from application.services.embedding_models import LOCAL_EMBEDDING_MODEL

    config = await container[WorkspaceEmbeddingConfigStore].get(workspace_id)
    return config.model if config else LOCAL_EMBEDDING_MODEL


@router.get("/embedding", status_code=status.HTTP_200_OK)
async def get_workspace_embedding(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> WorkspaceEmbeddingResponse:
    """The workspace's embedding model and whether the caller can use it."""
    from application.ports.embedding_generator import EmbeddingGenerator
    from application.services.embedding_models import EMBEDDING_MODELS, LOCAL_EMBEDDING_MODEL
    from application.services.llm_scope import UserLLMScope
    from infrastructure.config import Settings

    enabled = container[Settings].user_llm_keys_enabled
    model = (
        await _current_embedding_model(container, auth.workspace_id)
        if enabled
        else LOCAL_EMBEDDING_MODEL
    )
    spec = (
        await container[UserLLMScope].spec_for_model(model, auth.workspace_id, auth.user_id)
        if enabled
        else None
    )
    info = await container[EmbeddingGenerator].get_model_info()
    docs = await container[ArtifactReadModel].list_artifacts(
        workspace_id=auth.workspace_id, limit=1
    )
    return WorkspaceEmbeddingResponse(
        enabled=enabled,
        model=model,
        server_model=str(info.get("model_name", "")),
        has_documents=bool(docs),
        usable=spec is None or spec.missing_key_message is None,
        detail=spec.missing_key_message if spec else None,
        options=[
            EmbeddingModelOption(id=key, label=preset.label, providers=list(preset.providers))
            for key, preset in EMBEDDING_MODELS.items()
        ],
    )


@router.put("/embedding", status_code=status.HTTP_200_OK)
async def set_workspace_embedding(
    body: WorkspaceEmbeddingBody,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> WorkspaceEmbeddingUpdate:
    """Change the workspace's embedding model (admin). Re-embeds existing documents."""
    from application.ports.workspace_embedding_config import WorkspaceEmbeddingConfigStore
    from application.services.embedding_models import EMBEDDING_MODELS, LOCAL_EMBEDDING_MODEL
    from application.services.llm_scope import UserLLMScope
    from application.workflow_use_cases.trigger_bulk_reembed_use_case import (
        TriggerBulkReEmbedUseCase,
    )
    from infrastructure.config import Settings

    _require_admin(auth)
    if not container[Settings].user_llm_keys_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This DocuStore uses one embedding model for every workspace.",
        )
    if body.model != LOCAL_EMBEDDING_MODEL and body.model not in EMBEDDING_MODELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown embedding model '{body.model}'.",
        )
    if body.model == await _current_embedding_model(container, auth.workspace_id):
        return WorkspaceEmbeddingUpdate(model=body.model, reembed_workflows=0)

    has_documents = bool(
        await container[ArtifactReadModel].list_artifacts(workspace_id=auth.workspace_id, limit=1)
    )
    if has_documents and not body.reembed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Changing the embedding model re-embeds every document in this workspace.",
        )
    # The admin must be able to use what they pick — searching needs it right away.
    spec = await container[UserLLMScope].spec_for_model(
        body.model, auth.workspace_id, auth.user_id
    )
    if spec is not None and spec.missing_key_message:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail=spec.missing_key_message,
        )

    await container[WorkspaceEmbeddingConfigStore].set(
        auth.workspace_id, body.model, updated_by=auth.user_id
    )
    triggered = 0
    if has_documents:
        result = await container[TriggerBulkReEmbedUseCase].execute(
            workspace_id=auth.workspace_id, targets=["text", "summaries"]
        )
        triggered = result.triggered
    return WorkspaceEmbeddingUpdate(model=body.model, reembed_workflows=triggered)
