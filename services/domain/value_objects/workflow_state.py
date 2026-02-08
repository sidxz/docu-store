from enum import Enum


class WorkflowState(str, Enum):
    """Enumerate the possible states of a workflow run."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
