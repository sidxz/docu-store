from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum

from pydantic import BaseModel


class WorkflowStartedResponse(BaseModel):
    workflow_id: str
    status: str = "started"


class TemporalWorkflowInfo(BaseModel):
    workflow_id: str
    status: str  # "RUNNING", "COMPLETED", "FAILED", "TIMED_OUT", "NOT_FOUND"
    run_id: str | None = None
    started_at: datetime | None = None
    closed_at: datetime | None = None


class WorkflowTriggerReason(StrEnum):
    INITIAL_RUN = "initial_run"
    MANUAL_RERUN = "manual_rerun"
    FAILED_RETRY = "failed_retry"


class WorkflowNames(StrEnum):
    ARTIFACT_SAMPLE_WORKFLOW = "artifact_sample_workflow"
    COMPOUND_EXTRACTION_WORKFLOW = "compound_extraction_workflow"
    EMBEDDING_WORKFLOW = "embedding_workflow"
    SMILES_EMBEDDING_WORKFLOW = "smiles_embedding_workflow"
    PAGE_SUMMARIZATION_WORKFLOW = "page_summarization_workflow"
