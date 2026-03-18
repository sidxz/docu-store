import type { PubChemEnrichment } from "./types";

interface PubChemBadgeProps {
  enrichment: PubChemEnrichment | undefined;
}

export function PubChemBadge({ enrichment }: PubChemBadgeProps) {
  if (!enrichment) return null;
  if (enrichment.status === "error") return null;

  if (enrichment.status === "not_found") {
    return (
      <div className="flex items-center justify-between">
        <span className="text-text-muted">PubChem</span>
        <span className="text-text-muted">Not found</span>
      </div>
    );
  }

  if (!enrichment.pubchem_cid) return null;

  return (
    <div className="flex items-center justify-between">
      <span className="text-text-muted">PubChem</span>
      <a
        href={`https://pubchem.ncbi.nlm.nih.gov/compound/${enrichment.pubchem_cid}`}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium text-ds-info hover:underline"
      >
        CID: {enrichment.pubchem_cid} ↗
      </a>
    </div>
  );
}
