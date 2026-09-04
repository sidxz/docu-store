/**
 * Chat domain types — mirrors backend chat DTOs.
 */

import type { Bioactivity } from "./extraction";

/** Which chat surface a conversation belongs to. Fixed at creation: it decides
 *  which sidebar shows it and which corpus answers it, and a follow-up should
 *  not be able to switch either. */
export type ChatSurface = "research" | "literature";

// --- Source citations ---

/** A paper Europe PMC knows about, which this workspace may or may not hold. */
export interface LiteratureHit {
  external_id: string;
  source: string;
  title: string;
  doi: string | null;
  pmid: string | null;
  pmcid: string | null;
  abstract: string | null;
  journal: string | null;
  year: number | null;
  authors: string | null;
  licence: string | null;
  is_open_access: boolean;
  url: string;
  /** Whether this workspace may keep a copy. Decided from the licence, not the access flag. */
  is_ingestable: boolean;
  /** Why not, in words meant for a reader. Null when ingestable. */
  ingest_blocker: string | null;
  /** Europe PMC pubTypeList carries "Retracted Publication". */
  is_retracted: boolean;
  /** The retraction notice's own citation, when there is one. */
  retraction_notice: string | null;
  cited_by_count: number;
}

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
  /** "document" cites a page in this corpus; "literature" cites a paper the
   *  agent has only seen the abstract of. Render the two differently — an
   *  abstract-derived claim should not look as grounded as one read off a page,
   *  and its artifact_id points at nothing storable. */
  source_type?: "document" | "literature";
  /** Where to send a reader for a literature citation. Never a document route. */
  external_url?: string | null;
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

export interface ChartSeries {
  name: string;
  /** (x, y) pairs. x is a year on time panels, a category index otherwise. */
  points: [number, number][];
}

export type ChartPanel =
  | "timeline"
  | "evidence_mix"
  | "landmarks"
  | "stance"
  | "terms";

export interface ChartSpec {
  panel: ChartPanel;
  title: string;
  x_label: string;
  y_label: string;
  series: ChartSeries[];
  /** Tick labels when x is a category index. */
  categories: string[] | null;
  /** The incomplete x value — the current year. Rendered hatched. */
  partial_x: number | null;
  footnote: string | null;
  /** The Europe PMC query behind these counts. */
  source_query: string | null;
}

export interface ContentBlock {
  type: "text" | "table" | "molecule" | "citation_list" | "source_card" | "chart";
  content: string | null;
  headers: string[] | null;
  rows: string[][] | null;
  smiles: string | null;
  label: string | null;
  sources: SourceCitation[] | null;
  page_id: string | null;
  artifact_id: string | null;
  bioactivities: Bioactivity[] | null;
  chart: ChartSpec | null;
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
  /** Papers the literature searches returned for this message. Persisted so a
   *  reopened conversation can rebuild its panel — a citation whose panel is
   *  empty leads nowhere. */
  literature_results?: LiteratureHit[] | null;
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
  surface?: ChatSurface;
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
    | "literature_results"
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
  literature_results?: LiteratureHit[];
}

export interface GroundingStatus {
  is_grounded: boolean;
  confidence: number;
}
