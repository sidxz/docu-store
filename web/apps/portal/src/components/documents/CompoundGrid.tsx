import type { CompoundMention } from "@docu-store/types";
import type { PubChemEnrichment } from "@/plugins/pubchem";
import { MoleculeStructure } from "@docu-store/ui";
import { Card } from "@/components/ui/Card";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { CopySmiles } from "@/components/ui/CopySmiles";
import { PubChemBadge } from "@/plugins/pubchem";

interface CompoundGridProps {
  compounds: CompoundMention[];
  enrichmentBySmiles?: Map<string, PubChemEnrichment>;
}

export function CompoundGrid({
  compounds,
  enrichmentBySmiles,
}: CompoundGridProps) {
  return (
    <div className="mt-6">
      <h3 className="mb-3 text-sm font-medium text-text-secondary">
        Compound Mentions ({compounds.length})
      </h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {compounds.map((cm, i) => (
          <Card key={`${cm.smiles}-${i}`}>
            <div className="mb-3 flex justify-center border-b border-border-subtle pb-3">
              <MoleculeStructure
                smiles={cm.smiles}
                width={180}
                height={120}
              />
            </div>
            <div className="space-y-1.5 text-xs">
              <CopySmiles smiles={cm.smiles} />
              {cm.extracted_id && (
                <div className="flex items-center justify-between">
                  <span className="text-text-muted">ID</span>
                  <span className="font-medium text-text-primary">
                    {cm.extracted_id}
                  </span>
                </div>
              )}
              <div className="flex items-center justify-between">
                <span className="text-text-muted">Valid</span>
                {cm.is_smiles_valid === true ? (
                  <span className="text-ds-success">Yes</span>
                ) : cm.is_smiles_valid === false ? (
                  <span className="text-ds-error">No</span>
                ) : (
                  <span className="text-text-muted">—</span>
                )}
              </div>
              {cm.confidence != null && (
                <div className="flex items-center justify-between">
                  <span className="text-text-muted">Confidence</span>
                  <ScoreBadge score={cm.confidence} variant="pill" />
                </div>
              )}
              <PubChemBadge
                enrichment={enrichmentBySmiles?.get(
                  cm.canonical_smiles ?? "",
                )}
              />
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
