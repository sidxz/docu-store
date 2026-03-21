/**
 * Chat domain types — mirrors backend chat DTOs.
 */

// --- Source citations ---

export interface SourceCitation {
  artifact_id: string;
  artifact_title: string | null;
  authors: string[];
  presentation_date: string | null;
  page_id: string | null;
  page_index: number | null;
  page_name: string | null;
  text_excerpt: string | null;
  similarity_score: number | null;
  citation_index: number;
}

// --- Structured content blocks ---

export interface ContentBlock {
  type: "text" | "table" | "molecule" | "citation_list" | "source_card";
  content: string | null;
  headers: string[] | null;
  rows: string[][] | null;
  smiles: string | null;
  label: string | null;
  sources: SourceCitation[] | null;
}

// --- Agent tracing ---

export interface AgentStep {
  step: string;
  status: "started" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  input_summary: string | null;
  output_summary: string | null;
}

export interface AgentTrace {
  steps: AgentStep[];
  total_duration_ms: number | null;
  retry_count: number;
}

// --- Token usage ---

export interface TokenUsage {
  prompt: number;
  completion: number;
  total: number;
}

// --- Messages & conversations ---

export interface ChatMessage {
  conversation_id: string;
  message_id: string;
  role: "user" | "assistant";
  content: string;
  structured_content: ContentBlock[] | null;
  sources: SourceCitation[];
  agent_trace: AgentTrace | null;
  token_usage: TokenUsage | null;
  created_at: string;
}

export interface Conversation {
  conversation_id: string;
  workspace_id: string;
  owner_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  model_used: string | null;
  is_archived: boolean;
}

// --- SSE event types from the agent stream ---

export interface AgentEvent {
  type:
    | "step_started"
    | "step_completed"
    | "retrieval_results"
    | "token"
    | "structured_block"
    | "done"
    | "error";
  step?: string;
  status?: "started" | "completed" | "failed";
  description?: string;
  output?: string;
  delta?: string;
  sources?: SourceCitation[];
  block?: ContentBlock;
  message_id?: string;
  total_tokens?: number;
  duration_ms?: number;
  error_message?: string;
}
