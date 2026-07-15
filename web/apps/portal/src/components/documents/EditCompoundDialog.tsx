"use client";

import { useDeferredValue, useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import type { CompoundMention } from "@docu-store/types";
import { MoleculeStructure } from "@docu-store/ui";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { getErrorMessage } from "@/lib/api-error";
import type { CorrectedCompoundInput } from "@/hooks/use-pages";

interface EditCompoundDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** null = adding a new compound; otherwise the mention being edited (prefills the form). */
  compound: CompoundMention | null;
  /** Parent owns the full-list PUT — this only hands back the drafted single item. */
  onSave: (item: CorrectedCompoundInput) => Promise<void>;
}

/** hiledit: add/edit a single compound mention with a live RDKit structure preview. */
export function EditCompoundDialog({
  open,
  onOpenChange,
  compound,
  onSave,
}: EditCompoundDialogProps) {
  const initialLabel = compound?.extracted_id ?? "";
  const initialSmiles = compound?.smiles ?? "";

  const [label, setLabel] = useState(initialLabel);
  const [smiles, setSmiles] = useState(initialSmiles);
  const [saving, setSaving] = useState(false);

  // Reset the form to the target compound's values (or blank, for "add") each time the dialog opens.
  useEffect(() => {
    if (!open) return;
    setLabel(initialLabel);
    setSmiles(initialSmiles);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- snapshot the compound at open-time only; a prop change while open must not stomp in-flight edits
  }, [open]);

  const trimmedSmiles = smiles.trim();
  // Defer the structure render so fast typing in the SMILES input stays responsive.
  const deferredSmiles = useDeferredValue(trimmedSmiles);

  const handleSubmit = async () => {
    if (!trimmedSmiles || saving) return;
    setSaving(true);
    try {
      await onSave({
        smiles: trimmedSmiles,
        extracted_id: label.trim() || null,
        // Untouched provenance round-trips verbatim; add-mode has none yet.
        internal_id: compound?.internal_id ?? null,
        cdd_id: compound?.cdd_id ?? null,
        chembl_id: compound?.chembl_id ?? null,
        pdb_id: compound?.pdb_id ?? null,
      });
      // Success: the parent closes the dialog by flipping `open` (see CompoundGrid.handleSave).
    } catch (err) {
      // Keep the dialog open so the user can fix the SMILES and retry.
      toast.error("Failed to save compound", {
        description: getErrorMessage(err),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{compound ? "Edit compound" : "Add compound"}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="edit-compound-label">Label</Label>
            <Input
              id="edit-compound-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Compound 12"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="edit-compound-smiles">SMILES</Label>
            <Input
              id="edit-compound-smiles"
              value={smiles}
              onChange={(e) => setSmiles(e.target.value)}
              placeholder="c1ccccc1"
              className="font-mono"
            />
          </div>

          <div className="flex justify-center rounded-lg border border-border-subtle bg-surface-sunken py-3">
            <MoleculeStructure smiles={deferredSmiles} width={220} height={150} />
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={saving}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={!trimmedSmiles || saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
