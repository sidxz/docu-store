"""MongoDB adapter for the UserLLMConfigStore port (per-user BYO LLM keys).

Keys are Fernet-encrypted at rest; documents carry ``key_last4`` so the
settings UI never needs the plaintext. ``get()`` is the resolver path and maps
the user-facing provider id (``openrouter``) to what ``build_chat_model``
expects (``openai`` + base URL) via ``PRESETS``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from cryptography.fernet import Fernet, InvalidToken
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from application.ports.user_llm_config import UserLLMConfig, UserLLMProviderEntry
from application.services.llm_providers import PRESETS

log = structlog.get_logger(__name__)

_GENERATE_HINT = (
    "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
)


def user_llm_fernet(secret: str | None) -> Fernet:
    """The Fernet for USER_LLM_KEYS_SECRET, or a clear configuration error."""
    if not secret:
        msg = (
            "USER_LLM_KEYS_SECRET is required when USER_LLM_KEYS_ENABLED=true. "
            f"Generate one: {_GENERATE_HINT}"
        )
        raise ValueError(msg)
    try:
        return Fernet(secret)
    except ValueError as exc:
        msg = f"USER_LLM_KEYS_SECRET is not a valid Fernet key. Generate one: {_GENERATE_HINT}"
        raise ValueError(msg) from exc


def _query(workspace_id: UUID, user_id: UUID) -> dict:
    return {"workspace_id": str(workspace_id), "user_id": str(user_id)}


def _entry_doc(
    workspace_id: UUID,
    user_id: UUID,
    *,
    provider: str,
    api_key: str,
    model: str,
    chat_model: str,
    fernet: Fernet,
) -> dict:
    return {
        **_query(workspace_id, user_id),
        "provider": provider,
        "model": model,
        "chat_model": chat_model,
        "api_key_enc": fernet.encrypt(api_key.encode()).decode(),
        "key_last4": api_key[-4:],
        "updated_at": datetime.now(UTC),
    }


def _doc_to_entry(doc: dict) -> UserLLMProviderEntry:
    return UserLLMProviderEntry(
        provider=doc["provider"],
        model=doc["model"],
        chat_model=doc["chat_model"],
        key_last4=doc["key_last4"],
    )


def _doc_to_config(doc: dict, fernet: Fernet) -> UserLLMConfig:
    preset = PRESETS[doc["provider"]]
    return UserLLMConfig(
        provider=preset.provider,
        api_key=fernet.decrypt(doc["api_key_enc"].encode()).decode(),
        base_url=preset.base_url,
        model=doc["model"],
        chat_model=doc["chat_model"],
    )


class MongoUserLLMProviderStore:
    """One row per (workspace, user); the key is Fernet-encrypted."""

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
        collection_name: str = "user_llm_providers",
        *,
        fernet: Fernet,
    ) -> None:
        self._coll = client[db_name][collection_name]
        self._fernet = fernet

    async def get(self, workspace_id: UUID, user_id: UUID) -> UserLLMConfig | None:
        doc = await self._coll.find_one(_query(workspace_id, user_id))
        if doc is None:
            return None
        try:
            return _doc_to_config(doc, self._fernet)
        except InvalidToken:
            # Secret rotated without re-keying: resolve as "unconfigured" (the
            # call site fails closed) instead of crashing every enrichment.
            log.exception(
                "user_llm_providers.undecryptable",
                workspace_id=str(workspace_id),
                user_id=str(user_id),
            )
            return None

    async def get_entry(self, workspace_id: UUID, user_id: UUID) -> UserLLMProviderEntry | None:
        doc = await self._coll.find_one(_query(workspace_id, user_id))
        return _doc_to_entry(doc) if doc else None

    async def set(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        provider: str,
        api_key: str,
        model: str,
        chat_model: str,
    ) -> None:
        query = _query(workspace_id, user_id)
        doc = _entry_doc(
            workspace_id,
            user_id,
            provider=provider,
            api_key=api_key,
            model=model,
            chat_model=chat_model,
            fernet=self._fernet,
        )
        try:
            await self._coll.replace_one(query, doc, upsert=True)
        except DuplicateKeyError:
            # Two concurrent first-time upserts raced on the unique index;
            # the row exists now, so the retry takes the replace path.
            await self._coll.replace_one(query, doc, upsert=True)

    async def update_models(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        model: str,
        chat_model: str,
    ) -> bool:
        result = await self._coll.update_one(
            _query(workspace_id, user_id),
            {"$set": {"model": model, "chat_model": chat_model, "updated_at": datetime.now(UTC)}},
        )
        return result.matched_count == 1

    async def delete(self, workspace_id: UUID, user_id: UUID) -> None:
        await self._coll.delete_one(_query(workspace_id, user_id))

    async def ensure_indexes(self) -> None:
        await self._coll.create_index(
            [("workspace_id", 1), ("user_id", 1)],
            unique=True,
            name="idx_user_llm_ws_user",
        )
        log.info("user_llm_providers.indexes_created")
