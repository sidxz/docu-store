"""Per-workspace storage limit on uploaded bytes.

The effective limit is the lower of the workspace admin's limit and the
deployment cap (``MAX_WORKSPACE_STORAGE_MB``). Admins are not exempt: on a
self-serve deployment every signup owns their workspace.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.dtos.usage_dtos import WorkspaceStorage
from application.use_cases.storage_keys import workspace_prefix

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.blob_store import BlobStore
    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.workspace_storage_limit_store import WorkspaceStorageLimitStore

log = structlog.get_logger(__name__)

MIB = 1024 * 1024

# ponytail: per-process cache, so each API replica measures on its own; one
# listing of the workspace's files per refresh. Move to a background job if
# that gets slow. Module-level because lagom builds use cases per resolve.
_ON_DISK_TTL_S = 300.0
_ON_DISK_CACHE: dict[UUID, tuple[float, int]] = {}


def cap_bytes_from_settings(settings: object) -> int | None:
    mb = getattr(settings, "max_workspace_storage_mb", None)
    return None if mb is None else mb * MIB


def effective_storage_limit(limit_bytes: int | None, cap_bytes: int | None) -> int | None:
    """The lower of the two, ignoring whichever is unset; None = unlimited."""
    set_limits = [v for v in (limit_bytes, cap_bytes) if v is not None]
    return min(set_limits) if set_limits else None


def _mb(n: int) -> str:
    return f"{n / MIB:.1f} MB"


class CheckStorageQuotaUseCase:
    """Pre-flight gate for a file about to be stored in a workspace.

    ponytail: soft ceiling — usage counts only documents already projected
    into the read model, so concurrent uploads (or a stalled projector) can
    overshoot. Reserve bytes up front if that ever matters.
    """

    def __init__(
        self,
        limit_store: WorkspaceStorageLimitStore,
        artifact_read_model: ArtifactReadModel,
        cap_bytes: int | None,
    ) -> None:
        self._limits = limit_store
        self._artifacts = artifact_read_model
        self._cap = cap_bytes

    async def execute(self, workspace_id: UUID, incoming_bytes: int) -> Result[None, AppError]:
        try:
            limit_bytes = await self._limits.get_limit(workspace_id)
            limit = effective_storage_limit(limit_bytes, self._cap)
            if limit is None:
                return Success(None)
            used = await self._artifacts.sum_source_bytes(workspace_id)
        except Exception:
            # Same stance as the token quota: a broken read must not block uploads.
            log.warning("storage_quota.check_failed", workspace_id=str(workspace_id), exc_info=True)
            return Success(None)

        if used + incoming_bytes <= limit:
            return Success(None)

        message = (
            f"This workspace is out of storage: {_mb(used)} of {_mb(limit)} used, "
            f"and this file is {_mb(incoming_bytes)}. Delete documents to free space"
        )
        # An admin can only raise their own limit, never the deployment cap.
        cap_binds = self._cap is not None and (limit_bytes is None or limit_bytes >= self._cap)
        message += "." if cap_binds else ", or ask a workspace admin to raise the limit."
        return Failure(AppError("storage_full", message))


class GetWorkspaceStorageUseCase:
    """Uploaded bytes, disk use and the limits, for the admin Storage tab."""

    def __init__(
        self,
        limit_store: WorkspaceStorageLimitStore,
        artifact_read_model: ArtifactReadModel,
        blob_store: BlobStore,
        cap_bytes: int | None,
    ) -> None:
        self._limits = limit_store
        self._artifacts = artifact_read_model
        self._blobs = blob_store
        self._cap = cap_bytes

    async def execute(self, workspace_id: UUID) -> WorkspaceStorage:
        limit_bytes, uploaded = await asyncio.gather(
            self._limits.get_limit(workspace_id),
            self._artifacts.sum_source_bytes(workspace_id),
        )
        return WorkspaceStorage(
            uploaded_bytes=uploaded,
            on_disk_bytes=await self._on_disk(workspace_id),
            limit_bytes=limit_bytes,
            cap_bytes=self._cap,
            effective_limit_bytes=effective_storage_limit(limit_bytes, self._cap),
        )

    async def _on_disk(self, workspace_id: UUID) -> int | None:
        cached = _ON_DISK_CACHE.get(workspace_id)
        if cached and time.monotonic() - cached[0] < _ON_DISK_TTL_S:
            return cached[1]
        try:
            size = await asyncio.to_thread(self._blobs.total_size, workspace_prefix(workspace_id))
        except Exception:
            log.warning("storage.on_disk_failed", workspace_id=str(workspace_id), exc_info=True)
            return None
        _ON_DISK_CACHE[workspace_id] = (time.monotonic(), size)
        return size
