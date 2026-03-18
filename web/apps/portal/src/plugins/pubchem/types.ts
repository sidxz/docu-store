export interface PubChemEnrichment {
  canonical_smiles: string;
  pubchem_cid: number | null;
  iupac_name: string | null;
  molecular_formula: string | null;
  molecular_weight: number | null;
  status: "success" | "not_found" | "error";
}
