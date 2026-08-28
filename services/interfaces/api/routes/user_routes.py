"""User preferences and activity routes.

Not event-sourced. Simple operational metadata storage.
"""

from dataclasses import replace
from typing import Annotated

from duar_auth import RequestAuth
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from lagom import Container

from application.dtos.user_dtos import (
    AcceptTermsRequest,
    LLMLaneTestResult,
    LLMProviderEntry,
    LLMProviderPreset,
    LLMProviderRequest,
    LLMProviderResponse,
    LLMProviderTestRequest,
    LLMProviderTestResponse,
    RecentDocumentEntry,
    RecordDocumentOpenRequest,
    RecordSearchActivityRequest,
    SearchHistoryEntry,
    TermsStatusDTO,
    UpdatePreferencesRequest,
    UserPreferencesDTO,
)
from application.ports.repositories.terms_acceptance_store import TermsAcceptanceStore
from application.ports.repositories.user_activity_store import UserActivityStore
from application.ports.repositories.user_preferences_store import UserPreferencesStore
from application.ports.user_llm_config import UserLLMConfig, UserLLMConfigStore
from application.services.llm_providers import PRESETS
from infrastructure.config import Settings
from infrastructure.llm.provider_probe import probe_ner_support, probe_user_llm_config
from interfaces.dependencies import get_auth, get_container

router = APIRouter(prefix="/user", tags=["user"])


# ── Terms of Use / Privacy acceptance ────────────────────────────────────────


async def _terms_status(container: Container, auth: RequestAuth) -> TermsStatusDTO:
    settings = container[Settings]
    current = settings.terms_version
    if not settings.self_serve_enabled:
        # Internal/consortium deployments are covered by their own agreements.
        return TermsStatusDTO(required=False, current_version=current)
    accepted = await container[TermsAcceptanceStore].get_acceptance(auth.user_id)
    return TermsStatusDTO(
        required=accepted is None or accepted.version != current,
        current_version=current,
        accepted_version=accepted.version if accepted else None,
        accepted_at=accepted.accepted_at if accepted else None,
    )


@router.get("/terms", status_code=status.HTTP_200_OK)
async def get_terms_status(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> TermsStatusDTO:
    """Whether this caller still has to accept the current Terms/Privacy version."""
    return await _terms_status(container, auth)


@router.post("/terms/accept", status_code=status.HTTP_200_OK)
async def accept_terms(
    body: AcceptTermsRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> TermsStatusDTO:
    """Record acceptance. The client echoes the version it displayed, so a tab
    left open across a terms change cannot record assent to text never shown.
    """
    settings = container[Settings]
    if body.version != settings.terms_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="These terms have been updated. Reload and review the current version.",
        )
    await container[TermsAcceptanceStore].record_acceptance(auth.user_id, body.version)
    return await _terms_status(container, auth)


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


async def _suggestions_dto() -> dict[str, list[str]]:
    from infrastructure.llm.openrouter_catalog import suggested_models

    return {pid: list(await suggested_models(pid)) for pid in PRESETS}


def _require_user_keys(container: Container) -> Settings:
    settings = container[Settings]
    if not settings.user_llm_keys_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Per-user LLM providers are not enabled on this deployment.",
        )
    return settings


def _known_provider(provider: str) -> str:
    if provider not in PRESETS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider {provider!r}."
        )
    return provider


@router.get("/llm-provider", status_code=status.HTTP_200_OK)
async def get_llm_provider(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> LLMProviderResponse:
    """Every provider the caller has configured (never a key), plus form presets."""
    settings = container[Settings]
    entries = []
    if settings.user_llm_keys_enabled:
        entries = await container[UserLLMConfigStore].list_entries(auth.workspace_id, auth.user_id)
    return LLMProviderResponse(
        enabled=settings.user_llm_keys_enabled,
        configured=any(e.active for e in entries),
        providers=[
            LLMProviderEntry(
                provider=e.provider,
                model=e.model,
                chat_model=e.chat_model,
                key_last4=e.key_last4,
                active=e.active,
                updated_at=e.updated_at,
            )
            for e in entries
        ],
        presets=_presets_dto(),
        suggestions=await _suggestions_dto(),
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
    """Add or update one provider. With a key it becomes active; other providers are kept."""
    settings = _require_user_keys(container)
    store = container[UserLLMConfigStore]
    api_key = body.api_key.strip() if body.api_key is not None else None
    if api_key is not None and not 8 <= len(api_key) <= 512:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="api_key must be between 8 and 512 characters.",
        )
    preset = PRESETS[body.provider]
    model = body.model or preset.model
    chat_model = body.chat_model or preset.chat_model

    if api_key is None:
        stored = await store.get_config(auth.workspace_id, auth.user_id, body.provider)
        if stored is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No {body.provider} key stored — add one first.",
            )
        # Gate only what is about to run: editing an inactive entry's models is
        # free, and activating it later is where the capability check lands.
        active = await store.get_entry(auth.workspace_id, auth.user_id)
        if active is not None and active.provider == body.provider:
            await _require_ner_capable(
                replace(stored, model=model, chat_model=chat_model), settings
            )
        if not await store.update_models(
            auth.workspace_id,
            auth.user_id,
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
        auth.user_id,
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
    """Switch which stored provider everything runs on. One click back, too."""
    settings = _require_user_keys(container)
    store = container[UserLLMConfigStore]
    cfg = await store.get_config(auth.workspace_id, auth.user_id, _known_provider(provider))
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No {provider} key stored."
        )
    await _require_ner_capable(cfg, settings)
    await store.activate(auth.workspace_id, auth.user_id, provider)


@router.delete("/llm-provider/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_provider(
    provider: str,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    _require_user_keys(container)
    await container[UserLLMConfigStore].delete(
        auth.workspace_id, auth.user_id, _known_provider(provider)
    )


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
    never part of the request; only the stored one is ever used.
    """
    settings = _require_user_keys(container)
    cfg = await container[UserLLMConfigStore].get_config(
        auth.workspace_id, auth.user_id, _known_provider(provider)
    )
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No {provider} key stored."
        )
    if body is not None:
        preset = PRESETS[provider]
        cfg = replace(
            cfg,
            model=body.model or preset.model,
            chat_model=body.chat_model or preset.chat_model,
        )
    results = await probe_user_llm_config(cfg, allow_cloud=settings.allow_cloud_llm)
    lanes = {
        lane: LLMLaneTestResult(ok=ok, detail=detail) for lane, (ok, detail) in results.items()
    }
    return LLMProviderTestResponse(ok=all(r.ok for r in lanes.values()), lanes=lanes)
