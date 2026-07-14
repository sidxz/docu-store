"""DTOs for the token usage ledger (chat + ingestion accounting)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from application.dtos.chat_dtos import TokenUsageDTO


class TokenUsageEvent(BaseModel):
    """One append-only ledger entry: real provider-reported tokens for one unit of work.

    ``event_id`` (optional) becomes the Mongo ``_id`` so writers that need
    idempotency (live chat writes, the backfill script) can upsert on a
    deterministic key like ``chat:{message_id}``. Ingestion writers omit it —
    every retry attempt consumed real tokens and must append.
    """

    event_id: str | None = None
    workspace_id: UUID | None = None
    user_id: UUID | None = None
    kind: Literal["chat", "ingestion"]
    source: str  # chat_message | page_summary | artifact_summary | doc_metadata
    prompt: int = 0
    completion: int = 0
    total: int = 0
    model: str | None = None
    ref: str | None = None  # conversation_id / page_id / artifact_id
    created_at: datetime


class KindUsage(BaseModel):
    """Aggregated usage for one (member, kind) cell."""

    prompt: int = 0
    completion: int = 0
    total: int = 0
    event_count: int = 0


class MemberTokenUsage(BaseModel):
    """Per-member usage split by kind, for the admin stats view."""

    user_id: str | None
    chat: KindUsage = KindUsage()
    ingestion: KindUsage = KindUsage()
    total_tokens: int = 0


class TokenLimitEntry(BaseModel):
    """One token-limit row: a per-user override, or the workspace default when user_id is None.

    ``limit`` semantics: None = unlimited, 0 = fully blocked.
    """

    user_id: UUID | None = None
    limit: int | None = None


class MonthUsage(BaseModel):
    """Current-calendar-month usage (UTC) + the caller's effective limit."""

    chat: int = 0
    ingestion: int = 0
    total: int = 0
    limit: int | None = None  # None = unlimited


class UserTokenUsageResponse(TokenUsageDTO):
    """GET /chat/usage: requested-window totals + current-month block."""

    month: MonthUsage
