from enum import StrEnum


class WorkflowTriggerReason(StrEnum):
    INITIAL_RUN = "initial_run"
    MANUAL_RERUN = "manual_rerun"
    FAILED_RETRY = "failed_retry"


class WorkflowNames(StrEnum):
    ARTIFACT_SAMPLE_WORKFLOW = "artifact_sample_workflow"
    COMPOUND_EXTRACTION_WORKFLOW = "compound_extraction_workflow"
    EMBEDDING_WORKFLOW = "embedding_workflow"
    SMILES_EMBEDDING_WORKFLOW = "smiles_embedding_workflow"
