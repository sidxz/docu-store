"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Atom } from "lucide-react";
import { Button } from "primereact/button";
import { Message } from "primereact/message";

import { MoleculeStructure, StructureInput } from "@docu-store/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { CopySmiles } from "@/components/ui/CopySmiles";
import { EmptyState } from "@/components/ui/EmptyState";
import { useSearchCompounds } from "@/hooks/use-search";

interface CompoundResult {
  smiles: string;
  extracted_id?: string | null;
  similarity_score: number;
  confidence?: number | null;
  artifact_id: string;
  page_id: string;
  page_index: number;
  artifact_name?: string | null;
}

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
            label="Search"
            icon={search.isPending ? "pi pi-spin pi-spinner" : "pi pi-search"}
            onClick={handleSearch}
            disabled={!smiles.trim() || search.isPending}
          />
        </div>
      </Card>

      {/* Error */}
      {search.error && (
        <div className="mb-6">
          <Message
            severity="error"
            text="Compound search failed. Ensure the SMILES string is valid and the backend is running."
          />
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
              Model: {search.data.model_used}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {(search.data.results as CompoundResult[]).map((r, i) => (
              <Card key={`${r.smiles}-${i}`}>
                <div className="flex justify-center border-b border-border-subtle pb-3 mb-3">
                  <MoleculeStructure
                    smiles={r.smiles}
                    width={200}
                    height={140}
                  />
                </div>
                <div className="space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-text-muted">Similarity</span>
                    <ScoreBadge score={r.similarity_score} variant="pill" />
                  </div>
                  <CopySmiles smiles={r.smiles} maxWidth="max-w-[160px]" />
                  {r.extracted_id && (
                    <div className="flex items-center justify-between">
                      <span className="text-text-muted">ID</span>
                      <span className="font-medium text-text-primary">
                        {r.extracted_id}
                      </span>
                    </div>
                  )}
                  {r.confidence != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-text-muted">Confidence</span>
                      <ScoreBadge score={r.confidence} variant="pill" />
                    </div>
                  )}
                  <div className="flex items-center justify-between pt-1 border-t border-border-subtle">
                    <Link
                      href={`/${workspace}/documents/${r.artifact_id}`}
                      className="text-accent-text hover:underline"
                    >
                      {r.artifact_name ?? "Document"}
                    </Link>
                    <Link
                      href={`/${workspace}/documents/${r.artifact_id}/pages/${r.page_id}`}
                      className="text-text-muted hover:text-text-secondary"
                    >
                      Page {r.page_index}
                    </Link>
                  </div>
                </div>
              </Card>
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
