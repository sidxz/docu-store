"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { Atom, Search, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";

import { StructureInput } from "@docu-store/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { CompoundSearchResultDTO } from "@docu-store/types";
import { useSearchCompounds } from "@/hooks/use-search";
import { CompoundResultCard } from "@/components/compounds/CompoundResultCard";

export default function CompoundsPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const [smiles, setSmiles] = useState("");
  const search = useSearchCompounds();

  const handleSearch = () => {
    const trimmed = smiles.trim();
    if (!trimmed) return;
    search.mutate({ query_smiles: trimmed });
  };

  return (
    <div>
      <PageHeader
        icon={Atom}
        title="Compounds"
        subtitle="Search for structurally similar compounds by SMILES or draw a structure"
      />

      {/* Structure input */}
      <Card className="mb-6">
        <StructureInput value={smiles} onChange={setSmiles} />
        <div className="mt-4">
          <Button
            onClick={handleSearch}
            disabled={!smiles.trim() || search.isPending}
          >
            {search.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Search className="size-4" />
            )}
            Search
          </Button>
        </div>
      </Card>

      {/* Error */}
      {search.error && (
        <div className="mb-6">
          <Alert variant="destructive">
            <AlertCircle className="size-4" />
            <AlertDescription>Compound search failed. Ensure the SMILES string is valid and the backend is running.</AlertDescription>
          </Alert>
        </div>
      )}

      {/* Results — card grid */}
      {search.data && !search.isPending && (
        <div>
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm text-text-secondary">
              {search.data.total_results} result
              {search.data.total_results !== 1 ? "s" : ""} for{" "}
              <span className="font-mono text-xs text-text-primary">
                {search.data.query_smiles}
              </span>
            </p>
            <span className="text-xs text-text-muted">
              Model: <span className="font-mono">{search.data.model_used}</span>
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {(search.data.results as CompoundSearchResultDTO[]).map((r, i) => (
              <CompoundResultCard key={`${r.smiles}-${i}`} r={r} workspace={workspace} />
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!search.data && !search.isPending && (
        <EmptyState
          icon={Atom}
          title="Search compounds"
          description="Enter a SMILES string or draw a structure above to find similar compounds in your documents."
        />
      )}
    </div>
  );
}
