from enum import Enum


class WorkflowTriggerReason(str, Enum):
    INITIAL_RUN = "initial_run"
    MANUAL_RERUN = "manual_rerun"
    FAILED_RETRY = "failed_retry"
