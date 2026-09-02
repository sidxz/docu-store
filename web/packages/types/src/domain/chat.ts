/**
 * Chat domain types — mirrors backend chat DTOs.
 */

import type { Bioactivity } from "./extraction";

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

// --- Retrieval filters ---

/** One NER tag the planner ended up filtering retrieval by. */
export interface NerFilterTag {
  entity_text: string;
  entity_type: string;
}

/** Planning output kept on the assistant message. `ner_entities` is the running
 *  filter list after accumulation and drops — what retrieval actually ran with,
 *  not everything NER found. */
export interface QueryContext {
  ner_entities: NerFilterTag[];
  authors: string[];
  query_type: string;
  reformulated_query: string;
  grounded: boolean;
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
  page_id: string | null;
  artifact_id: string | null;
  bioactivities: Bioactivity[] | null;
}

// --- Agent tracing ---

export interface AgentStep {
  step: string;
  status: "started" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  input_summary: string | null;
  output_summary: string | null;
  thinking_content: string | null;
}

export interface ThinkingBlock {
  label: string;
  step: string;
  content: string;
}

export interface AgentTrace {
  steps: AgentStep[];
  thinking_blocks?: ThinkingBlock[];
  reasoning_content?: string;
  total_duration_ms: number | null;
  retry_count: number;
  grounding_is_grounded: boolean | null;
  grounding_confidence: number | null;
}

// --- Token usage ---

export interface TokenUsage {
  prompt: number;
  completion: number;
  total: number;
  /** What the provider reported answering with — the resolved name, comma-joined
   *  if the turn used more than one. Null on messages predating this. */
  model: string | null;
}

export interface MonthTokenUsage {
  chat: number;
  ingestion: number;
  total: number;
  limit: number | null;
}

/** GET /chat/usage — requested-window totals + current-calendar-month block. */
export interface UserTokenUsage extends TokenUsage {
  month?: MonthTokenUsage;
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
  query_context?: QueryContext | null;
  created_at: string;
}

export interface Conversation {
  conversation_id: string;
  workspace_id: string;
  owner_id: string;
  title: string | null;
  folder_id: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  model_used: string | null;
  is_archived: boolean;
  /** True while an answer is being generated server-side (detail endpoint only). */
  active_run?: boolean;
}

// --- Chat folders (per-user, per-workspace, flat) ---

export interface ChatFolder {
  folder_id: string;
  workspace_id: string;
  owner_id: string;
  name: string;
  created_at: string;
  updated_at: string;
  chat_count: number;
}

// --- Recent chats (dashboard panel) ---

export interface EntityRef {
  text: string;
  type: string;
}

export interface CitedDocument {
  artifact_id: string;
  title: string | null;
}

export interface RecentConversation extends Conversation {
  last_answer_snippet: string | null;
  entities: EntityRef[];
  cited_documents: CitedDocument[];
  source_count: number;
  grounded: boolean | null;
  grounded_confidence: number | null;
}

// --- SSE event types from the agent stream ---

export interface AgentEvent {
  type:
    | "step_started"
    | "step_completed"
    | "retrieval_results"
    | "token"
    | "reasoning_token"
    | "structured_block"
    | "grounding_result"
    | "query_context"
    | "done"
    | "error";
  step?: string;
  status?: "started" | "completed" | "failed";
  description?: string;
  output?: string;
  thinking_content?: string;
  thinking_label?: string;
  delta?: string;
  sources?: SourceCitation[];
  block?: ContentBlock;
  message_id?: string;
  total_tokens?: number;
  model?: string;
  duration_ms?: number;
  error_message?: string;
  grounding_is_grounded?: boolean;
  grounding_confidence?: number;
  query_context_entities?: NerFilterTag[];
}

export interface GroundingStatus {
  is_grounded: boolean;
  confidence: number;
}
