"""MongoDB adapter for the UserLLMConfigStore port (per-user BYO LLM keys).

One document per (workspace, user, provider); exactly one of a user's documents
carries ``active: True`` and that is the one ``get()`` resolves. Keys are
Fernet-encrypted at rest and documents carry ``key_last4``, so the settings UI
never needs the plaintext. ``get()`` maps the user-facing provider id
(``openrouter``) to what ``build_chat_model`` expects (``openai`` + base URL)
via ``PRESETS``.
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


def _query(
    workspace_id: UUID,
    user_id: UUID,
    provider: str | None = None,
    *,
    active: bool | None = None,
) -> dict:
    q: dict = {"workspace_id": str(workspace_id), "user_id": str(user_id)}
    if provider is not None:
        q["provider"] = provider
    if active is not None:
        q["active"] = active
    return q


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
        **_query(workspace_id, user_id, provider),
        "active": True,
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
        active=bool(doc.get("active")),
        updated_at=doc.get("updated_at"),
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
    """One document per (workspace, user, provider); the key is Fernet-encrypted."""

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
        return await self._config(_query(workspace_id, user_id, active=True), workspace_id, user_id)

    async def get_config(
        self,
        workspace_id: UUID,
        user_id: UUID,
        provider: str,
    ) -> UserLLMConfig | None:
        return await self._config(
            _query(workspace_id, user_id, provider), workspace_id, user_id
        )

    async def _config(self, query: dict, workspace_id: UUID, user_id: UUID) -> UserLLMConfig | None:
        doc = await self._coll.find_one(query)
        if doc is None:
            return None
        try:
            return _doc_to_config(doc, self._fernet)
        except (InvalidToken, KeyError):
            # Secret rotated without re-keying, or the stored provider isn't in
            # PRESETS (e.g. deprecated/renamed): resolve as "unconfigured" (the
            # call site fails closed) instead of crashing every enrichment.
            log.exception(
                "user_llm_providers.unresolvable",
                workspace_id=str(workspace_id),
                user_id=str(user_id),
            )
            return None

    async def get_entry(self, workspace_id: UUID, user_id: UUID) -> UserLLMProviderEntry | None:
        doc = await self._coll.find_one(_query(workspace_id, user_id, active=True))
        return _doc_to_entry(doc) if doc else None

    async def list_entries(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> list[UserLLMProviderEntry]:
        cursor = self._coll.find(_query(workspace_id, user_id)).sort("updated_at", -1)
        return [_doc_to_entry(doc) async for doc in cursor]

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
        """Upsert this provider and make it active. Every other provider is kept."""
        query = _query(workspace_id, user_id, provider)
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
        await self._deactivate_others(workspace_id, user_id, provider)

    async def update_models(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        provider: str,
        model: str,
        chat_model: str,
    ) -> bool:
        result = await self._coll.update_one(
            _query(workspace_id, user_id, provider),
            {"$set": {"model": model, "chat_model": chat_model, "updated_at": datetime.now(UTC)}},
        )
        return result.matched_count == 1

    async def activate(self, workspace_id: UUID, user_id: UUID, provider: str) -> bool:
        result = await self._coll.update_one(
            _query(workspace_id, user_id, provider),
            {"$set": {"active": True}},
        )
        if result.matched_count != 1:
            return False
        await self._deactivate_others(workspace_id, user_id, provider)
        return True

    async def delete(self, workspace_id: UUID, user_id: UUID, provider: str) -> bool:
        """Forget one provider. Deleting the active one deliberately leaves none active:
        picking the replacement is the user's call, and the settings page says so.
        """
        result = await self._coll.delete_one(_query(workspace_id, user_id, provider))
        return result.deleted_count == 1

    async def _deactivate_others(self, workspace_id: UUID, user_id: UUID, provider: str) -> None:
        # ponytail: two writes, no transaction. A crash between them leaves either
        # two actives (get() picks one, both work) or — after a failed activate —
        # none, which the settings page shows and one click fixes. Neither loses a
        # key, so a session is not worth the weight.
        await self._coll.update_many(
            {**_query(workspace_id, user_id), "provider": {"$ne": provider}},
            {"$set": {"active": False}},
        )

    async def ensure_indexes(self) -> None:
        """Create the (workspace, user, provider) index, retiring the single-slot one.

        The original unique index was on (workspace, user), which does not just
        fail to describe a registry — it forbids one, rejecting the second
        provider a user adds. Dropping it and backfilling ``active`` are both
        idempotent, so every deployment converts itself on the next start.
        """
        existing = await self._coll.index_information()
        if "idx_user_llm_ws_user" in existing:
            await self._coll.drop_index("idx_user_llm_ws_user")
            log.info("user_llm_providers.single_slot_index_dropped")
        await self._coll.create_index(
            [("workspace_id", 1), ("user_id", 1), ("provider", 1)],
            unique=True,
            name="idx_user_llm_ws_user_provider",
        )
        # Rows written before the registry have no `active`, and get() reads
        # active-only — so they must be adopted, not left invisible.
        result = await self._coll.update_many(
            {"active": {"$exists": False}},
            {"$set": {"active": True}},
        )
        if result.modified_count:
            log.info("user_llm_providers.adopted_pre_registry_rows", count=result.modified_count)
        log.info("user_llm_providers.indexes_created")
