"""User preferences and activity routes.

Not event-sourced. Simple operational metadata storage.
"""

from dataclasses import replace
from typing import Annotated

from duar_auth import RequestAuth
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from lagom import Container

from application.dtos.user_dtos import (
    LLMLaneTestResult,
    LLMProviderPreset,
    LLMProviderRequest,
    LLMProviderResponse,
    LLMProviderTestResponse,
    RecentDocumentEntry,
    RecordDocumentOpenRequest,
    RecordSearchActivityRequest,
    SearchHistoryEntry,
    UpdatePreferencesRequest,
    UserPreferencesDTO,
)
from application.ports.repositories.user_activity_store import UserActivityStore
from application.ports.repositories.user_preferences_store import UserPreferencesStore
from application.ports.user_llm_config import UserLLMConfig, UserLLMConfigStore
from application.services.llm_providers import PRESETS
from infrastructure.config import Settings
from infrastructure.llm.provider_probe import probe_ner_support, probe_user_llm_config
from interfaces.dependencies import get_auth, get_container

router = APIRouter(prefix="/user", tags=["user"])


# ── Preferences ──────────────────────────────────────────────────────────────


@router.get("/preferences", status_code=status.HTTP_200_OK)
async def get_preferences(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> UserPreferencesDTO:
    store = container[UserPreferencesStore]
    return await store.get_preferences(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
    )


@router.patch("/preferences", status_code=status.HTTP_200_OK)
async def update_preferences(
    body: UpdatePreferencesRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> UserPreferencesDTO:
    store = container[UserPreferencesStore]
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return await store.get_preferences(
            workspace_id=auth.workspace_id,
            user_id=auth.user_id,
        )
    return await store.update_preferences(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        updates=updates,
    )


# ── Activity Recording ───────────────────────────────────────────────────────


@router.post("/activity/search", status_code=status.HTTP_204_NO_CONTENT)
async def record_search(
    body: RecordSearchActivityRequest,
    background_tasks: BackgroundTasks,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    store = container[UserActivityStore]
    background_tasks.add_task(
        store.record_search,
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        query_text=body.query_text,
        search_mode=body.search_mode,
        result_count=body.result_count,
    )


@router.post("/activity/document", status_code=status.HTTP_204_NO_CONTENT)
async def record_document_open(
    body: RecordDocumentOpenRequest,
    background_tasks: BackgroundTasks,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    store = container[UserActivityStore]
    background_tasks.add_task(
        store.record_document_open,
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        artifact_id=body.artifact_id,
        artifact_title=body.artifact_title,
    )


# ── Activity Deletion ─────────────────────────────────────────────────────────


@router.delete("/activity/searches", status_code=status.HTTP_204_NO_CONTENT)
async def clear_search_history(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Delete all search history for the authenticated user."""
    store = container[UserActivityStore]
    await store.clear_search_history(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
    )


@router.delete("/activity/searches/{query_text}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search_entry(
    query_text: str,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Delete a single search history entry by query text."""
    store = container[UserActivityStore]
    await store.delete_search_entry(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        query_text=query_text,
    )


# ── Activity Queries ─────────────────────────────────────────────────────────


@router.get("/activity/searches", status_code=status.HTTP_200_OK)
async def get_recent_searches(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SearchHistoryEntry]:
    store = container[UserActivityStore]
    return await store.get_recent_searches(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        limit=limit,
    )


@router.get("/activity/documents", status_code=status.HTTP_200_OK)
async def get_recent_documents(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    limit: int = Query(default=20, ge=1, le=100),
) -> list[RecentDocumentEntry]:
    store = container[UserActivityStore]
    return await store.get_recent_documents(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        limit=limit,
    )


# ── BYO LLM provider ─────────────────────────────────────────────────────────


def _presets_dto() -> dict[str, LLMProviderPreset]:
    return {
        pid: LLMProviderPreset(model=p.model, chat_model=p.chat_model) for pid, p in PRESETS.items()
    }


def _require_user_keys(container: Container) -> Settings:
    settings = container[Settings]
    if not settings.user_llm_keys_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Per-user LLM providers are not enabled on this deployment.",
        )
    return settings


@router.get("/llm-provider", status_code=status.HTTP_200_OK)
async def get_llm_provider(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> LLMProviderResponse:
    """The caller's provider (never the key) plus presets for the settings UI."""
    settings = container[Settings]
    entry = None
    if settings.user_llm_keys_enabled:
        entry = await container[UserLLMConfigStore].get_entry(auth.workspace_id, auth.user_id)
    return LLMProviderResponse(
        enabled=settings.user_llm_keys_enabled,
        configured=entry is not None,
        provider=entry.provider if entry else None,
        key_last4=entry.key_last4 if entry else None,
        model=entry.model if entry else None,
        chat_model=entry.chat_model if entry else None,
        presets=_presets_dto(),
    )


async def _require_ner_capable(cfg: UserLLMConfig, settings: Settings) -> None:
    """Refuse a config whose ingestion model cannot run entity extraction.

    Entity extraction is not an optional lane here — a document ingested without
    it is missing most of what makes it findable — so a model that rejects the
    structured-output request NER makes must never reach storage. Only an outright
    provider refusal blocks: a timeout or a 5xx still saves, or an outage would
    lock the user out of the very settings page they need to fix it.
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
    settings = _require_user_keys(container)
    store = container[UserLLMConfigStore]
    api_key = body.api_key.strip() if body.api_key is not None else None
    if api_key is not None and not 8 <= len(api_key) <= 512:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="api_key must be between 8 and 512 characters.",
        )
    if api_key is None:
        entry = await store.get_entry(auth.workspace_id, auth.user_id)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No LLM provider configured — add a key first.",
            )
        preset = PRESETS[entry.provider]
        model = body.model or preset.model
        chat_model = body.chat_model or preset.chat_model
        stored = await store.get(auth.workspace_id, auth.user_id)
        if stored is not None:
            await _require_ner_capable(
                replace(stored, model=model, chat_model=chat_model), settings
            )
        if not await store.update_models(
            auth.workspace_id,
            auth.user_id,
            model=model,
            chat_model=chat_model,
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No LLM provider configured — add a key first.",
            )
        return
    preset = PRESETS[body.provider]
    model = body.model or preset.model
    chat_model = body.chat_model or preset.chat_model
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
        auth.user_id,
        provider=body.provider,
        api_key=api_key,
        model=model,
        chat_model=chat_model,
    )


@router.delete("/llm-provider", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_provider(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    _require_user_keys(container)
    await container[UserLLMConfigStore].delete(auth.workspace_id, auth.user_id)


@router.post("/llm-provider/test", status_code=status.HTTP_200_OK)
async def probe_llm_provider(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> LLMProviderTestResponse:
    """Probe the *stored* config — one tiny completion per distinct lane model."""
    settings = _require_user_keys(container)
    cfg = await container[UserLLMConfigStore].get(auth.workspace_id, auth.user_id)
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No LLM provider configured."
        )
    results = await probe_user_llm_config(cfg, allow_cloud=settings.allow_cloud_llm)
    lanes = {
        lane: LLMLaneTestResult(ok=ok, detail=detail) for lane, (ok, detail) in results.items()
    }
    return LLMProviderTestResponse(ok=all(r.ok for r in lanes.values()), lanes=lanes)
