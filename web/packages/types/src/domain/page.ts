/**
 * Page types — mirrors backend page DTOs.
 * Mirrors: services/application/dtos/page_dtos.py
 */
import type {
  CompoundMention,
  HumanCorrectionInfo,
  SummaryCandidate,
  TagMention,
  TextMention,
} from "./extraction";

export interface PageResponse {
  page_id: string;
  artifact_id: string;
  name: string;
  index: number;
  compound_mentions: CompoundMention[];
  tag_mentions: TagMention[];
  text_mention: TextMention | null;
  summary_candidate: SummaryCandidate | null;
  human_corrections?: Record<string, HumanCorrectionInfo>;
}

export interface CreatePageRequest {
  name: string;
  artifact_id: string;
  index?: number;
}
