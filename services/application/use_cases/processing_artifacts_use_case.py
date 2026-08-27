"""Which of the caller's documents are still moving through the pipeline.

Feeds the topbar "processing" badge: one row per artifact with a percent
(completed / observed workflows), a coarse stage, and whether it is active.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from application.dtos.workflow_dtos import ProcessingArtifactResponse

if TYPE_CHECKING:
    from application.dtos.artifact_dtos import ArtifactResponse
    from application.dtos.workflow_dtos import TemporalWorkflowInfo
    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.workflow_orchestrator import WorkflowOrchestrator

GRACE = timedelta(seconds=90)  # keep a row while the next pipeline stage spins up
FAILED_WINDOW = timedelta(hours=24)  # idle-but-failed rows stay visible this long
RECENT_LIMIT = 10  # ponytail: own most-recently-updated artifacts probed per poll
SCAN_LIMIT = 50  # workspace rows fetched before the owner filter

_FAILED = frozenset({"FAILED", "TIMED_OUT", "TERMINATED", "CANCELED"})
_UNOBSERVED = frozenset({"NOT_FOUND", "UNKNOWN"})
# First stage whose kinds intersect the running set wins.
_STAGES: tuple[tuple[str, frozenset[str]], ...] = (
    ("parsing", frozenset({"parse"})),
    (
        "extracting",
        frozenset(
            {
                "ner",
                "doc_metadata",
                "page_summarization",
                "artifact_summarization",
            },
        ),
    ),
    ("extracting_structures", frozenset({"compound_extraction"})),  # CSER on page images
    (
        "indexing",
        frozenset(
            {
                "embedding",
                "page_summary_embedding",
                "artifact_summary_embedding",
                "smiles_embedding",
                "batch_reembed",
            },
        ),
    ),
    ("finishing", frozenset({"tag_aggregation", "reconcile_compound_labels"})),
)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def summarize(
    artifact_id: UUID,
    source_filename: str | None,
    statuses: dict[str, TemporalWorkflowInfo],
    now: datetime,
) -> ProcessingArtifactResponse:
    """Fold per-workflow statuses into one row. Keys are ``<kind>`` or ``<kind>:<page_id>``."""
    observed = {n: i for n, i in statuses.items() if i.status not in _UNOBSERVED}
    completed = sum(i.status == "COMPLETED" for i in observed.values())
    failed = sum(i.status in _FAILED for i in observed.values())
    running_kinds = {n.split(":", 1)[0] for n, i in observed.items() if i.status == "RUNNING"}
    running = sum(i.status == "RUNNING" for i in observed.values())
    total = len(observed)
    last_close = max((_utc(i.closed_at) for i in observed.values() if i.closed_at), default=None)
    active = running > 0 or (last_close is not None and now - last_close < GRACE)
    if running:
        stage = next((s for s, kinds in _STAGES if kinds & running_kinds), "finishing")
    elif failed:
        stage = "failed"
    else:
        stage = "finishing"
    return ProcessingArtifactResponse(
        artifact_id=str(artifact_id),
        source_filename=source_filename,
        total=total,
        completed=completed,
        running=running,
        failed=failed,
        percent=round(100 * completed / total) if total else 0,
        stage=stage,
        active=active,
        last_activity_at=last_close,
    )


class ListProcessingArtifactsUseCase:
    def __init__(
        self,
        artifact_read_model: ArtifactReadModel,
        orchestrator: WorkflowOrchestrator,
    ) -> None:
        self._read_model = artifact_read_model
        self._orchestrator = orchestrator

    async def execute(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
        now: datetime | None = None,
    ) -> list[ProcessingArtifactResponse]:
        """The caller's own artifacts that are active, or failed within FAILED_WINDOW."""
        now = now or datetime.now(UTC)
        # Processing keeps bumping updated_at, so active documents sort first.
        artifacts = await self._read_model.list_artifacts(
            workspace_id=workspace_id,
            skip=0,
            limit=SCAN_LIMIT,
            allowed_artifact_ids=allowed_artifact_ids,
            sort_by="updated_at",
            sort_order=-1,
        )
        mine = [a for a in artifacts if a.owner_id == user_id][:RECENT_LIMIT]
        rows = await asyncio.gather(*(self._row(a, now) for a in mine))
        return [
            r
            for r in rows
            if r.active
            or (r.failed and r.last_activity_at and now - r.last_activity_at < FAILED_WINDOW)
        ]

    async def _row(self, artifact: ArtifactResponse, now: datetime) -> ProcessingArtifactResponse:
        page_ids = [p if isinstance(p, UUID) else p.page_id for p in (artifact.pages or [])]
        statuses = await self._orchestrator.get_artifact_pipeline_statuses(
            artifact.artifact_id,
            page_ids,
        )
        return summarize(artifact.artifact_id, artifact.source_filename, statuses, now)
