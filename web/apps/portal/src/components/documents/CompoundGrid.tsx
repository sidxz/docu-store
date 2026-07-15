"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Plus, Trash2 } from "lucide-react";

import type { CompoundMention, HumanCorrectionInfo } from "@docu-store/types";
import type { PubChemEnrichment } from "@/plugins/pubchem";
import { MoleculeStructure } from "@docu-store/ui";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/button";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { CopySmiles } from "@/components/ui/CopySmiles";
import { PubChemBadge } from "@/plugins/pubchem";
import { useConfirm } from "@/components/providers/ConfirmProvider";
import { useCorrectPageCompounds, type CorrectedCompoundInput } from "@/hooks/use-pages";
import { HumanCorrectedBadge } from "@/components/documents/HumanCorrectedBadge";
import { EditCompoundDialog } from "@/components/documents/EditCompoundDialog";

interface CompoundGridProps {
  compounds: CompoundMention[];
  enrichmentBySmiles?: Map<string, PubChemEnrichment>;
  /** hiledit: enables per-card edit/delete + an "Add compound" card. Requires `pageId`. */
  editable?: boolean;
  pageId?: string;
  /** Shown next to the section heading when a human has corrected this page's compound mentions. */
  humanCorrection?: HumanCorrectionInfo | null;
}

/** Strips derived/server-computed fields (canonical_smiles, is_smiles_valid, confidence, ...) —
 *  the backend recomputes those on every save. */
function toCorrectedInput(cm: CompoundMention): CorrectedCompoundInput {
  return {
    smiles: cm.smiles,
    extracted_id: cm.extracted_id,
    internal_id: cm.internal_id,
    cdd_id: cm.cdd_id,
    chembl_id: cm.chembl_id,
    pdb_id: cm.pdb_id,
  };
}

type EditorState = "add" | { index: number };

export function CompoundGrid({
  compounds,
  enrichmentBySmiles,
  editable = false,
  pageId,
  humanCorrection,
}: CompoundGridProps) {
  const [editor, setEditor] = useState<EditorState | null>(null);
  const confirm = useConfirm();
  const correctMutation = useCorrectPageCompounds(pageId ?? "");

  // Every save is a full-list PUT: splice the drafted item into (or onto) the
  // current list, built from the *fetched* mentions so untouched cards round-trip verbatim.
  const handleSave = async (item: CorrectedCompoundInput) => {
    const base = compounds.map(toCorrectedInput);
    const next =
      editor && editor !== "add"
        ? base.map((c, i) => (i === editor.index ? item : c))
        : [...base, item];
    await correctMutation.mutateAsync({ compound_mentions: next });
    toast.success(editor === "add" ? "Compound added" : "Compound updated");
    setEditor(null);
  };

  const handleDelete = async (index: number, cm: CompoundMention) => {
    const ok = await confirm({
      title: "Delete compound?",
      description: `Remove ${cm.extracted_id ?? cm.smiles} from this page? This can't be undone.`,
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!ok) return;

    const next = compounds.filter((_, i) => i !== index).map(toCorrectedInput);
    try {
      await correctMutation.mutateAsync({ compound_mentions: next });
      toast.success("Compound removed");
    } catch (err) {
      toast.error("Failed to remove compound", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  };

  const editingCompound =
    editor && editor !== "add" ? (compounds[editor.index] ?? null) : null;

  return (
    <div className="mt-6">
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-sm font-medium text-text-secondary">
          Compound Mentions ({compounds.length})
        </h3>
        {humanCorrection && <HumanCorrectedBadge info={humanCorrection} />}
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {compounds.map((cm, i) => (
          <Card
            key={`${cm.smiles}-${i}`}
            className={editable ? "group/cm relative" : undefined}
          >
            {editable && (
              <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover/cm:opacity-100">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  aria-label="Edit compound"
                  onClick={() => setEditor({ index: i })}
                >
                  <Pencil className="size-3.5" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  aria-label="Delete compound"
                  onClick={() => handleDelete(i, cm)}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            )}
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
                  <span className="font-mono font-medium text-text-primary">
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

        {editable && (
          <button
            type="button"
            onClick={() => setEditor("add")}
            className="flex min-h-[220px] flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed border-border-default text-text-muted transition-colors hover:border-primary/40 hover:text-primary"
          >
            <Plus className="size-5" />
            <span className="text-sm font-medium">Add compound</span>
          </button>
        )}
      </div>

      {editable && (
        <EditCompoundDialog
          open={editor !== null}
          onOpenChange={(open) => !open && setEditor(null)}
          compound={editingCompound}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
