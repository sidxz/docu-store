from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from domain.value_objects.workflow_state import WorkflowState


class WorkflowStatus(BaseModel):
    """Value object representing the state of a workflow run.

    Immutable value object that tracks workflow progress with intelligent
    properties for state queries and timing calculations.
    """

    workflow_id: UUID | None = None
    """Unique identifier for the workflow run. Optional, but can be useful for tracking."""

    state: WorkflowState | None = None
    """Current state of the workflow run (e.g., PENDING, IN_PROGRESS, COMPLETED, FAILED)."""

    message: str | None = None
    """Optional message providing additional context about the workflow status."""

    progress: float | None = None
    """Progress percentage (0.0 to 1.0). None if not applicable."""

    started_at: datetime | None = None
    """Timestamp when the workflow run started."""

    completed_at: datetime | None = None
    """Timestamp when the workflow run completed (success or failure)."""

    @field_validator("progress")
    @classmethod
    def validate_progress(cls, v: float | None) -> float | None:
        """Ensure progress is between 0.0 and 1.0 if provided."""
        if v is not None and not (0.0 <= v <= 1.0):
            msg = "progress must be between 0.0 and 1.0"
            raise ValueError(msg)
        return v

    @field_validator("completed_at")
    @classmethod
    def validate_completion_times(cls, v: datetime | None, info: object) -> datetime | None:
        """Ensure completed_at >= started_at if both are provided."""
        data = info.data
        if v is not None and data.get("started_at") is not None and v < data["started_at"]:
            msg = "completed_at must be after or equal to started_at"
            raise ValueError(msg)
        return v

    model_config = {"frozen": True}  # Immutable value object

    # ========================================================================
    # STATE QUERY PROPERTIES
    # ========================================================================

    @property
    def is_pending(self) -> bool:
        """Check if workflow is in pending state."""
        return self.state == WorkflowState.PENDING

    @property
    def is_in_progress(self) -> bool:
        """Check if workflow is currently running."""
        return self.state == WorkflowState.IN_PROGRESS

    @property
    def is_completed(self) -> bool:
        """Check if workflow finished successfully."""
        return self.state == WorkflowState.COMPLETED

    @property
    def is_failed(self) -> bool:
        """Check if workflow encountered an error."""
        return self.state == WorkflowState.FAILED

    @property
    def is_terminal(self) -> bool:
        """Check if workflow is in a terminal state (COMPLETED or FAILED)."""
        return self.is_completed or self.is_failed

    # ========================================================================
    # TIMING PROPERTIES
    # ========================================================================

    @property
    def elapsed_seconds(self) -> float | None:
        """Get elapsed time in seconds.

        Returns:
            Elapsed time in seconds if started_at is set, None otherwise.
            Uses current time if still in progress, completed_at if finished.

        """
        if self.started_at is None:
            return None

        end_time = self.completed_at if self.completed_at else datetime.now(UTC)
        return (end_time - self.started_at).total_seconds()

    @property
    def elapsed_formatted(self) -> str | None:
        """Get human-readable elapsed time (e.g., '1h 23m 45s').

        Returns:
            Formatted string or None if not started.

        """
        elapsed = self.elapsed_seconds
        if elapsed is None:
            return None

        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    @property
    def progress_percentage(self) -> float:
        """Get progress as a percentage (0-100).

        Returns:
            Progress percentage, or 0 if progress is None or PENDING.

        """
        if self.progress is None or self.is_pending:
            return 0.0
        return self.progress * 100.0

    # ========================================================================
    # FACTORY METHODS
    # ========================================================================

    @classmethod
    def pending(
        cls,
        message: str | None = None,
        workflow_id: UUID | None = None,
    ) -> "WorkflowStatus":
        """Create a pending workflow status."""
        return cls(
            state=WorkflowState.PENDING,
            message=message,
            workflow_id=workflow_id,
        )

    @classmethod
    def in_progress(
        cls,
        message: str | None = None,
        progress: float | None = None,
        started_at: datetime | None = None,
        workflow_id: UUID | None = None,
    ) -> "WorkflowStatus":
        """Create an in-progress workflow status."""
        return cls(
            workflow_id=workflow_id,
            state=WorkflowState.IN_PROGRESS,
            message=message,
            progress=progress,
            started_at=started_at or datetime.now(UTC),
        )

    @classmethod
    def completed(
        cls,
        message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        workflow_id: UUID | None = None,
    ) -> "WorkflowStatus":
        """Create a completed workflow status."""
        return cls(
            workflow_id=workflow_id,
            state=WorkflowState.COMPLETED,
            message=message,
            progress=1.0,
            started_at=started_at,
            completed_at=completed_at or datetime.now(UTC),
        )

    @classmethod
    def failed(
        cls,
        message: str,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        workflow_id: UUID | None = None,
    ) -> "WorkflowStatus":
        """Create a failed workflow status."""
        return cls(
            workflow_id=workflow_id,
            state=WorkflowState.FAILED,
            message=message,
            progress=None,
            started_at=started_at,
            completed_at=completed_at or datetime.now(UTC),
        )
