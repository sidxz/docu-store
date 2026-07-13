"""Ingestion-side token usage recording (page/artifact summaries, doc metadata).

The Artifact aggregate is already loaded at every enrichment LLM call site and
carries workspace_id/owner_id — so attribution needs no Temporal or event
schema changes. NER (structflo-ner → langextract) is deliberately NOT counted:
it bypasses the LLM client layer and exposes no usage in its return type.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from application.dtos.usage_dtos import TokenUsageEvent
from infrastructure.llm.token_counter import TokenCounter

if TYPE_CHECKING:
    from application.ports.token_usage_store import TokenUsageStore
    from domain.aggregates.artifact import Artifact

log = structlog.get_logger(__name__)


def ingestion_counter(artifact: Artifact, *, source: str) -> TokenCounter:
    """Counter carrying the uploader's identity, for Langfuse + the ledger."""
    return TokenCounter(
        user_id=str(artifact.owner_id) if artifact.owner_id else None,
        session_id=str(artifact.id),
        workspace_id=str(artifact.workspace_id) if artifact.workspace_id else None,
        tags=["ingestion", source],
    )


async def record_ingestion_usage(
    store: TokenUsageStore | None,
    counter: TokenCounter,
    *,
    artifact: Artifact,
    source: str,
    ref: str,
    model: str | None = None,
) -> None:
    """Append one ledger event for an enrichment run. Never raises — a ledger
    hiccup must not fail the pipeline. No event_id: Temporal retries consumed
    real tokens, so every attempt appends.
    """
    if store is None or counter.total_tokens <= 0:
        return
    try:
        await store.record(
            TokenUsageEvent(
                workspace_id=artifact.workspace_id,
                user_id=artifact.owner_id,
                kind="ingestion",
                source=source,
                prompt=counter.prompt_tokens,
                completion=counter.completion_tokens,
                total=counter.total_tokens,
                model=model,
                ref=ref,
                created_at=datetime.now(UTC),
            ),
        )
    except Exception:
        log.exception("ingestion.usage.record_failed", source=source, ref=ref)
