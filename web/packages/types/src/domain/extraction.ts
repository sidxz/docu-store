/**
 * Extraction metadata — shared base for all AI-extracted data.
 * Mirrors: services/domain/value_objects/extraction_metadata.py
 */
export interface ExtractionMetadata {
  confidence: number | null;
  date_extracted: string | null;
  model_name: string | null;
  additional_model_params: Record<string, string> | null;
  pipeline_run_id: string | null;
}

export interface TextMention extends ExtractionMetadata {
  text: string;
}

export interface TitleMention extends ExtractionMetadata {
  title: string;
}

export interface TagSource {
  page_id: string;
  page_index: number;
  confidence: number | null;
}

export interface TagMention extends ExtractionMetadata {
  tag: string;
  entity_type: string | null;
  /** Lowercase key for grouping — populated on artifact-level aggregated tags. */
  tag_normalized: string | null;
  /** Pages that contributed this tag to the artifact aggregate. */
  sources: TagSource[] | null;
  /** Highest confidence across all source pages. */
  max_confidence: number | null;
  /** Number of distinct pages where this tag was found. */
  page_count: number | null;
}

export interface CompoundMention extends ExtractionMetadata {
  smiles: string;
  canonical_smiles: string | null;
  is_smiles_valid: boolean | null;
  // Cross-database identifiers resolved during extraction:
  internal_id: string | null;   // DAIKON internal compound registry
  cdd_id: string | null;        // Collaborative Drug Discovery Vault
  chembl_id: string | null;     // ChEMBL
  pdb_id: string | null;        // RCSB Protein Data Bank
  other_ids: string[] | null;   // Any additional identifiers not categorized above
  extracted_id: string | null;  // Raw ID string as found in the source document
  // Pixel coordinates [x1, y1, x2, y2] on the CSER render (artifacts/{id}/pages/{index}_cser.png).
  // Meaningless without that image, which is why it's persisted, never re-derived.
  structure_bbox: number[] | null;
  label_bbox: number[] | null;
  structure_confidence: number | null;
  label_confidence: number | null;
}

export interface AuthorMention extends ExtractionMetadata {
  name: string;
}

export interface PresentationDate extends ExtractionMetadata {
  date: string;
  source: string | null;
}

export interface SummaryCandidate extends ExtractionMetadata {
  summary: string | null;
  is_locked: boolean;
  hil_correction: string | null;
}

export interface Bioactivity {
  assay_type: string;
  value: string;
  unit: string;
  raw_text: string;
}

export interface EmbeddingMetadata {
  model_name: string | null;
  dimensions: number | null;
  generated_at: string | null;
  algorithm: string | null;
  additional_params: Record<string, string> | null;
}

/** Mirrors services/application/dtos/correction_dtos.py:HumanCorrectionInfo */
export interface HumanCorrectionInfo {
  corrected_by_id: string;
  corrected_by_name?: string | null;
  corrected_at: string;
}
