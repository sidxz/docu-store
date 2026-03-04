/**
 * Artifact types — mirrors backend artifact DTOs.
 * Mirrors: services/application/dtos/artifact_dtos.py
 */
import type { SummaryCandidate, TitleMention } from "./extraction";
import type { PageResponse } from "./page";

export type ArtifactType =
  | "GENERIC_PRESENTATION"
  | "SCIENTIFIC_PRESENTATION"
  | "RESEARCH_ARTICLE"
  | "SCIENTIFIC_DOCUMENT"
  | "DISCLOSURE_DOCUMENT"
  | "MINUTE_OF_MEETING"
  | "UNCLASSIFIED";

export type MimeType =
  | "application/pdf"
  | "application/vnd.ms-powerpoint"
  | "application/vnd.openxmlformats-officedocument.presentationml.presentation"
  | "application/msword"
  | "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export interface ArtifactResponse {
  artifact_id: string;
  source_uri: string | null;
  source_filename: string | null;
  artifact_type: ArtifactType;
  mime_type: MimeType;
  storage_location: string;
  // `pages` is a union because the backend returns either embedded PageResponse
  // objects (when ?include_pages=true) or bare page ID strings (default list).
  pages: string[] | PageResponse[] | null;
  title_mention: TitleMention | null;
  tags: string[];
  summary_candidate: SummaryCandidate | null;
}

export interface CreateArtifactRequest {
  artifact_id?: string;
  source_uri?: string;
  source_filename?: string;
  artifact_type: ArtifactType;
  mime_type: MimeType;
  storage_location: string;
}

/**
 * Flat summary DTO embedded inside search results.
 * Lighter than ArtifactResponse — no page objects or mention detail.
 */
export interface ArtifactDetailsDTO {
  artifact_id: string;
  source_uri: string | null;
  source_filename: string | null;
  artifact_type: string;
  mime_type: string;
  storage_location: string;
  page_count: number;
  tags: string[];
  summary: string | null;
  title: string | null;
}
