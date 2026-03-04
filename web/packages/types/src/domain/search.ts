/**
 * Search types — mirrors backend search DTOs.
 * Mirrors: services/application/dtos/search_dtos.py,
 *          services/application/dtos/embedding_dtos.py,
 *          services/application/dtos/smiles_embedding_dtos.py
 */
import type { ArtifactDetailsDTO } from "./artifact";

// --- Text chunk search ---

export interface SearchRequest {
  query_text: string;
  limit?: number;
  artifact_id?: string;
  score_threshold?: number;
}

export interface SearchResultDTO {
  page_id: string;
  artifact_id: string;
  page_index: number;
  similarity_score: number;
  text_preview: string | null;
  artifact_name: string | null;
  artifact_details: ArtifactDetailsDTO | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResultDTO[];
  total_results: number;
  model_used: string;
}

// --- Summary search ---

export interface SummarySearchRequest {
  query_text: string;
  limit?: number;
  entity_type?: "page" | "artifact";
  artifact_id?: string;
  score_threshold?: number;
}

export interface SummarySearchResultDTO {
  entity_type: "page" | "artifact";
  entity_id: string;
  artifact_id: string;
  similarity_score: number;
  summary_text: string | null;
  artifact_title: string | null;
  metadata: Record<string, unknown>;
}

export interface SummarySearchResponse {
  query: string;
  results: SummarySearchResultDTO[];
  total_results: number;
  model_used: string;
}

// --- Hierarchical search ---

export interface HierarchicalSearchRequest {
  query_text: string;
  limit?: number;
  score_threshold?: number;
  include_chunks?: boolean;
}

export interface ChunkHit {
  page_id: string;
  artifact_id: string;
  page_index: number;
  score: number;
  text_preview: string | null;
}

export interface SummaryHit {
  entity_type: "page" | "artifact";
  entity_id: string;
  artifact_id: string;
  score: number;
  summary_text: string | null;
  artifact_title: string | null;
}

export interface HierarchicalSearchResponse {
  query: string;
  summary_hits: SummaryHit[];
  chunk_hits: ChunkHit[];
  total_summary_hits: number;
  total_chunk_hits: number;
  model_used: string;
}

// --- Compound search ---

export interface CompoundSearchRequest {
  query_smiles: string;
  limit?: number;
  artifact_id?: string;
  score_threshold?: number;
}

export interface CompoundSearchResultDTO {
  smiles: string;
  canonical_smiles: string | null;
  extracted_id: string | null;
  confidence: number | null;
  similarity_score: number;
  page_id: string;
  page_index: number;
  artifact_id: string;
  artifact_name: string | null;
}

export interface CompoundSearchResponse {
  query_smiles: string;
  query_canonical_smiles: string | null;
  results: CompoundSearchResultDTO[];
  total_results: number;
  model_used: string;
}
