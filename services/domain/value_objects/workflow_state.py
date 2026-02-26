from enum import StrEnum


class WorkflowState(StrEnum):
    """Enumerate the possible states of a workflow run."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
