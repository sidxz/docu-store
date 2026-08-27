"""Conflict-safe aggregate writes for use cases whose expensive work happens
between loading an aggregate and saving it.

Root cause this exists for: the Artifact and Page streams have many concurrent
writers (per-page tag aggregation, summarization, metadata extraction, NER).
A use case that loads an aggregate, spends a minute on an LLM call, then saves,
presents a stream version that is often stale by then → ``ConcurrencyError`` →
Temporal retries the whole activity, LLM call included, and frequently collides
again. Here the load happens right before the write, so the optimistic-lock
window is milliseconds, and a conflict costs a re-read, not a re-run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from domain.exceptions import ConcurrencyError

if TYPE_CHECKING:
    from collections.abc import Callable

log = structlog.get_logger(__name__)


def commit(
    repository: Any,
    aggregate_id: Any,
    mutate: Callable[[Any], bool],
    *,
    attempts: int = 3,
) -> Any | None:
    """Load fresh → ``mutate`` → save; on ``ConcurrencyError`` reload and try again.

    ``mutate`` receives the freshly loaded aggregate and returns whether it
    changed it; False skips the save. Returns the saved aggregate, or None when
    nothing changed. The last conflict propagates — the activity retry policy
    remains the outer safety net.
    """
    for attempt in range(1, attempts + 1):
        aggregate = repository.get_by_id(aggregate_id)
        if not mutate(aggregate):
            return None
        try:
            repository.save(aggregate)
        except ConcurrencyError:
            if attempt == attempts:
                raise
            log.info(
                "aggregate_commit.conflict_retry",
                aggregate_id=str(aggregate_id),
                attempt=attempt,
            )
            continue
        return aggregate
    return None  # pragma: no cover — loop always returns or raises
