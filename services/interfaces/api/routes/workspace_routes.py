"""Workspace routes.

Duar member/group proxies, admin token limits, and the workspace's BYO LLM
providers and embedding model (self-serve).
"""

import asyncio
from dataclasses import replace
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
from application.dtos.user_dtos import (
    LLMLaneTestResult,
    LLMProviderEntry,
    LLMProviderPreset,
    LLMProviderRequest,
    LLMProviderResponse,
    LLMProviderTestRequest,
    LLMProviderTestResponse,
)
from application.ports.blob_store import BlobStore
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.page_read_models import PageReadModel
from application.ports.token_limit_store import TokenLimitStore
from application.ports.user_llm_config import UserLLMConfig, UserLLMConfigStore
from application.services.llm_providers import PRESETS, ProviderPreset
from application.use_cases.cser_export_use_case import build_cser_export_zip
from infrastructure.config import Settings
from infrastructure.llm.provider_probe import probe_ner_support, probe_user_llm_config
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
    usable: bool  # the workspace holds a key that can serve ``model``
    detail: str | None = None  # why not, when not
    options: list[EmbeddingModelOption]


class WorkspaceEmbeddingBody(BaseModel):
    model: str
    # Required to change the model of a workspace that already has documents:
    # every one of them is re-embedded (with the workspace's key).
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
    """The workspace's embedding model and whether its keys can serve it."""
    from application.ports.embedding_generator import EmbeddingGenerator
    from application.services.embedding_models import EMBEDDING_MODELS, LOCAL_EMBEDDING_MODEL
    from application.services.llm_scope import UserLLMScope

    enabled = container[Settings].user_llm_keys_enabled
    model = (
        await _current_embedding_model(container, auth.workspace_id)
        if enabled
        else LOCAL_EMBEDDING_MODEL
    )
    spec = (
        await container[UserLLMScope].spec_for_model(model, auth.workspace_id) if enabled else None
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
    # The workspace must hold a key for what is picked — searching needs it right
    # away, and the re-embed below runs on it.
    spec = await container[UserLLMScope].spec_for_model(body.model, auth.workspace_id)
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


# ── BYO LLM provider ─────────────────────────────────────────────────────────


def _offered(settings: Settings) -> dict[str, ProviderPreset]:
    """Providers a workspace may add or switch to; TAMU AI only where the deployment opts in."""
    return {pid: p for pid, p in PRESETS.items() if pid != "tamu" or settings.tamu_ai_enabled}


def _presets_dto(settings: Settings) -> dict[str, LLMProviderPreset]:
    return {
        pid: LLMProviderPreset(model=p.model, chat_model=p.chat_model)
        for pid, p in _offered(settings).items()
    }


async def _suggestions_dto(settings: Settings) -> dict[str, list[str]]:
    from infrastructure.llm.openrouter_catalog import suggested_models

    return {
        pid: list(p.models or await suggested_models(pid)) for pid, p in _offered(settings).items()
    }


def _chosen_models(provider: str, model: str | None, chat_model: str | None) -> tuple[str, str]:
    """Blank → the preset's default; a provider with a fixed model list allows nothing else."""
    preset = PRESETS[provider]
    picked = (model or preset.model, chat_model or preset.chat_model)
    if preset.models and not set(picked) <= set(preset.models):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{provider} offers only these models: {', '.join(preset.models)}.",
        )
    return picked


def _require_user_keys(container: Container) -> Settings:
    settings = container[Settings]
    if not settings.user_llm_keys_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace LLM providers are not enabled on this deployment.",
        )
    return settings


def _known_provider(provider: str, presets: dict[str, ProviderPreset] = PRESETS) -> str:
    if provider not in presets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider {provider!r}."
        )
    return provider


@router.get("/llm-provider", status_code=status.HTTP_200_OK)
async def get_llm_provider(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> LLMProviderResponse:
    """Every provider the workspace has configured (never a key), plus form presets.

    Any member may read it — to know whether the workspace can upload and chat —
    but only admins see a key's last four characters or may change anything.
    """
    settings = container[Settings]
    entries = []
    if settings.user_llm_keys_enabled:
        entries = await container[UserLLMConfigStore].list_entries(auth.workspace_id)
    return LLMProviderResponse(
        enabled=settings.user_llm_keys_enabled,
        configured=any(e.active for e in entries),
        can_manage=auth.is_admin,
        providers=[
            LLMProviderEntry(
                provider=e.provider,
                model=e.model,
                chat_model=e.chat_model,
                key_last4=e.key_last4 if auth.is_admin else "",
                active=e.active,
                updated_at=e.updated_at,
            )
            for e in entries
        ],
        presets=_presets_dto(settings),
        suggestions=await _suggestions_dto(settings),
    )


async def _require_ner_capable(cfg: UserLLMConfig, settings: Settings) -> None:
    """Refuse a config that cannot run entity extraction from becoming the active one.

    Entity extraction is not an optional lane here — a document ingested without
    it is missing most of what makes it findable — so a model that rejects the
    structured-output request NER makes must never be what ingestion runs on.
    Only an outright provider refusal blocks: a timeout or a 5xx still saves, or
    an outage would stop someone configuring their way out of it.

    Storing an entry is not gated, only activating one. Adding a provider you
    cannot use costs nothing while it sits inactive, and being able to add it is
    what lets you test it.
    """
    probe = await probe_ner_support(cfg, allow_cloud=settings.allow_cloud_llm)
    if probe.refused:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"This model cannot run entity extraction, which this workspace "
            f"requires: {probe.detail}",
        )


@router.put("/llm-provider", status_code=status.HTTP_204_NO_CONTENT)
async def set_llm_provider(
    body: LLMProviderRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Add or update one provider (admin). With a key it becomes active; others are kept."""
    _require_admin(auth)
    settings = _require_user_keys(container)
    store = container[UserLLMConfigStore]
    api_key = body.api_key.strip() if body.api_key is not None else None
    if api_key is not None and not 8 <= len(api_key) <= 512:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="api_key must be between 8 and 512 characters.",
        )
    preset = PRESETS[_known_provider(body.provider, _offered(settings))]
    model, chat_model = _chosen_models(body.provider, body.model, body.chat_model)

    if api_key is None:
        stored = await store.get_config(auth.workspace_id, body.provider)
        if stored is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No {body.provider} key stored — add one first.",
            )
        # Gate only what is about to run: editing an inactive entry's models is
        # free, and activating it later is where the capability check lands.
        active = await store.get_entry(auth.workspace_id)
        if active is not None and active.provider == body.provider:
            await _require_ner_capable(
                replace(stored, model=model, chat_model=chat_model), settings
            )
        if not await store.update_models(
            auth.workspace_id,
            provider=body.provider,
            model=model,
            chat_model=chat_model,
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No {body.provider} key stored — add one first.",
            )
        return

    await _require_ner_capable(
        UserLLMConfig(
            provider=preset.provider,
            api_key=api_key,
            base_url=preset.base_url,
            model=model,
            chat_model=chat_model,
        ),
        settings,
    )
    await store.set(
        auth.workspace_id,
        provider=body.provider,
        api_key=api_key,
        model=model,
        chat_model=chat_model,
    )


@router.post("/llm-provider/{provider}/activate", status_code=status.HTTP_204_NO_CONTENT)
async def activate_llm_provider(
    provider: str,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Switch which stored provider everything runs on (admin). One click back, too."""
    _require_admin(auth)
    settings = _require_user_keys(container)
    store = container[UserLLMConfigStore]
    cfg = await store.get_config(auth.workspace_id, _known_provider(provider, _offered(settings)))
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No {provider} key stored."
        )
    await _require_ner_capable(cfg, settings)
    await store.activate(auth.workspace_id, provider)


@router.delete("/llm-provider/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_provider(
    provider: str,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    _require_admin(auth)
    _require_user_keys(container)
    await container[UserLLMConfigStore].delete(auth.workspace_id, _known_provider(provider))


@router.post("/llm-provider/{provider}/test", status_code=status.HTTP_200_OK)
async def probe_llm_provider(
    provider: str,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    body: LLMProviderTestRequest | None = None,
) -> LLMProviderTestResponse:
    """Probe one stored provider — active or not, so it can be tried before switching.

    Models may be overridden per request. Testing is how you find out whether a
    model works, so requiring it to be saved first would have the order backwards:
    you would have to commit to a model to learn it was the wrong one. The key is
    never part of the request; only the stored one is ever used. Admin only: a
    probe spends the workspace's key.
    """
    _require_admin(auth)
    settings = _require_user_keys(container)
    cfg = await container[UserLLMConfigStore].get_config(
        auth.workspace_id, _known_provider(provider, _offered(settings))
    )
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No {provider} key stored."
        )
    if body is not None:
        model, chat_model = _chosen_models(provider, body.model, body.chat_model)
        cfg = replace(cfg, model=model, chat_model=chat_model)
    results = await probe_user_llm_config(cfg, allow_cloud=settings.allow_cloud_llm)
    lanes = {
        lane: LLMLaneTestResult(ok=ok, detail=detail) for lane, (ok, detail) in results.items()
    }
    return LLMProviderTestResponse(ok=all(r.ok for r in lanes.values()), lanes=lanes)
