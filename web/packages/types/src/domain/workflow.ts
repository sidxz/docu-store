/**
 * Workflow types — mirrors backend workflow DTOs.
 * Mirrors: services/application/dtos/workflow_dtos.py
 */

export interface WorkflowStartedResponse {
  workflow_id: string;
  status: string;
}

export type WorkflowStatus =
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "TIMED_OUT"
  | "NOT_FOUND";

export interface TemporalWorkflowInfo {
  workflow_id: string;
  status: WorkflowStatus;
  run_id: string | null;
  started_at: string | null;
  closed_at: string | null;
}

export type WorkflowTriggerReason =
  | "initial_run"
  | "manual_rerun"
  | "failed_retry";

/**
 * Temporal workflow names used as Workflow IDs (prefixed with entity ID).
 *  artifact_sample_workflow     — PDF parsing + page creation
 *  compound_extraction_workflow — CSER compound extraction from a page
 *  embedding_workflow           — text chunk embedding for a page
 *  smiles_embedding_workflow    — SMILES vector embedding for compound mentions
 *  page_summarization_workflow  — LLM summarization of a single page
 */
export type WorkflowName =
  | "artifact_sample_workflow"
  | "compound_extraction_workflow"
  | "embedding_workflow"
  | "smiles_embedding_workflow"
  | "page_summarization_workflow";

/** Shape of the workflow endpoint response (untyped in OpenAPI schema) */
export interface WorkflowMap {
  workflows?: Record<string, { workflow_id: string; status: string }>;
}
