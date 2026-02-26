from enum import Enum


class WorkflowTriggerReason(str, Enum):
    INITIAL_RUN = "initial_run"
    MANUAL_RERUN = "manual_rerun"
    FAILED_RETRY = "failed_retry"


class WorkflowNames(str, Enum):
    ARTIFACT_SAMPLE_WORKFLOW = "artifact_sample_workflow"
    COMPOUND_EXTRACTION_WORKFLOW = "compound_extraction_workflow"
    EMBEDDING_WORKFLOW = "embedding_workflow"
