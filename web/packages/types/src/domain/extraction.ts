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

export interface TagMention extends ExtractionMetadata {
  tag: string;
  entity_type: string | null;
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
}

export interface SummaryCandidate extends ExtractionMetadata {
  summary: string | null;
  is_locked: boolean;
  hil_correction: string | null;
}

export interface EmbeddingMetadata {
  model_name: string | null;
  dimensions: number | null;
  generated_at: string | null;
  algorithm: string | null;
  additional_params: Record<string, string> | null;
}
