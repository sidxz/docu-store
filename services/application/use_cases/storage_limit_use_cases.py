"""Per-workspace storage limit on uploaded bytes.

The effective limit is the lower of the workspace admin's limit and the
deployment cap (``MAX_WORKSPACE_STORAGE_MB``). Admins are not exempt: on a
self-serve deployment every signup owns their workspace.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.workspace_storage_limit_store import WorkspaceStorageLimitStore

log = structlog.get_logger(__name__)

MIB = 1024 * 1024


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
