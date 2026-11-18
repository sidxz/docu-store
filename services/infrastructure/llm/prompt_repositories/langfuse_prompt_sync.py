"""Publish the bundled prompts to Langfuse.

Each release ships its prompts in ``default_prompts/``; this keeps Langfuse in
step with them, so a deployment never seeds prompts from outside.

The version this code last published carries the ``bundled`` label. A prompt is
published again only when the bundled template differs from that version, so:

- a restart changes nothing;
- a prompt edited in the Langfuse UI stays in use (the app reads ``latest``)
  until a release ships a changed version of that same prompt, which then takes
  over while the edit stays in the prompt's history.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from langfuse.api import NotFoundError

from infrastructure.llm.prompt_repositories.bundled_prompts import bundled_prompts

log = structlog.get_logger(__name__)

BUNDLED_LABEL = "bundled"


def sync_bundled_prompts(
    client: Any,
    release: str,
    prompts: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """Bring Langfuse in step with ``prompts`` (default: the bundled ones).

    Returns the prompt names by outcome: ``created`` (a new version), ``adopted``
    (an identical version was already there, it only got the label) and
    ``unchanged``. Every prompt is attempted; if any failed, raises
    ``RuntimeError`` afterwards so the caller can retry.
    """
    prompts = bundled_prompts() if prompts is None else prompts
    result: dict[str, list[str]] = {"created": [], "adopted": [], "unchanged": []}
    failed: dict[str, Exception] = {}
    for name, template in prompts.items():
        try:
            result[_sync_one(client, name, template, release)].append(name)
        except Exception as exc:  # one bad prompt must not stop the rest
            failed[name] = exc
    if failed:
        name, exc = next(iter(failed.items()))
        msg = f"{len(failed)} of {len(prompts)} prompts not synced, first {name!r}: {exc}"
        raise RuntimeError(msg) from exc
    return result


def _sync_one(client: Any, name: str, template: str, release: str) -> str:
    shipped = _get(client, name, BUNDLED_LABEL)
    if shipped is not None and shipped.prompt == template:
        return "unchanged"

    latest = _get(client, name, "latest")
    if shipped is None and latest is not None and latest.prompt == template:
        # Seeded from outside before this existed: same text, so only mark it.
        labels = [label for label in latest.labels if label != "latest"]
        client.update_prompt(name=name, version=latest.version, new_labels=[*labels, BUNDLED_LABEL])
        return "adopted"

    if shipped is not None and latest is not None and latest.version != shipped.version:
        log.warning(
            "langfuse_prompt_sync.superseding_edit",
            name=name,
            edited_version=latest.version,
            release=release,
        )
    client.create_prompt(
        name=name,
        prompt=template,
        labels=[BUNDLED_LABEL, "production"],
        type="text",
        commit_message=f"docu-store {release}",
    )
    return "created"


def _get(client: Any, name: str, label: str) -> Any | None:
    """The version carrying ``label``, or None when there is none."""
    try:
        return client.api.prompts.get(name, label=label)
    except NotFoundError:
        return None


def start_bundled_prompt_sync(settings: Any) -> asyncio.Task[None] | None:
    """Start the sync in the background; None when Langfuse is not the prompt store.

    Call from the one process that owns the sync (the API). Starting it in several
    is harmless: racing syncs can only add duplicate identical versions.
    """
    try:
        if settings.prompt_repository_type != "langfuse":
            return None
        if not (settings.langfuse_public_key and settings.langfuse_secret_key):
            return None
        return asyncio.create_task(keep_syncing_bundled_prompts(settings))
    except Exception as exc:  # startup must never depend on this
        log.warning("langfuse_prompt_sync.not_started", error=str(exc))
        return None


async def keep_syncing_bundled_prompts(settings: Any, retry_seconds: float = 60) -> None:
    """Sync once, retrying until Langfuse takes it. Raises nothing but cancellation."""
    while True:
        try:
            from infrastructure.health.gpu_info import _get_app_version

            release = _get_app_version()
            result = await asyncio.to_thread(sync_bundled_prompts, _client(settings), release)
        except Exception as exc:  # Langfuse down or misconfigured: the app runs on its fallback
            log.warning("langfuse_prompt_sync.failed", error=str(exc), retry_seconds=retry_seconds)
            await asyncio.sleep(retry_seconds)
        else:
            log.info(
                "langfuse_prompt_sync.done",
                release=release,
                created=result["created"],
                adopted=result["adopted"],
                unchanged=len(result["unchanged"]),
            )
            return


def _client(settings: Any) -> Any:
    from langfuse import Langfuse

    return Langfuse(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )
