"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Button } from "primereact/button";
import { Column } from "primereact/column";
import { DataTable } from "primereact/datatable";
import { InputText } from "primereact/inputtext";
import { ProgressSpinner } from "primereact/progressspinner";
import { Tag } from "primereact/tag";

import { useSearchCompounds } from "@/hooks/use-search";

export default function CompoundsPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const [smiles, setSmiles] = useState("");
  const search = useSearchCompounds();

  const handleSearch = () => {
    const trimmed = smiles.trim();
    if (!trimmed) return;
    search.mutate({ query_smiles: trimmed });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Compounds</h1>
      <p className="mt-1 text-sm text-gray-500">
        Search for structurally similar compounds by SMILES notation.
      </p>

      {/* Search bar */}
      <div className="mt-6 flex gap-3">
        <div className="flex-1">
          <InputText
            value={smiles}
            onChange={(e) => setSmiles(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter SMILES string, e.g. CC(=O)Oc1ccccc1C(=O)O"
            className="w-full font-mono"
          />
        </div>
        <Button
          label="Search"
          icon="pi pi-search"
          onClick={handleSearch}
          loading={search.isPending}
          disabled={!smiles.trim()}
        />
      </div>

      {/* Loading */}
      {search.isPending && (
        <div className="mt-8 flex items-center justify-center">
          <ProgressSpinner style={{ width: "40px", height: "40px" }} />
        </div>
      )}

      {/* Error */}
      {search.error && (
        <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Compound search failed. Ensure the SMILES string is valid and the
          backend is running.
        </div>
      )}

      {/* Results */}
      {search.data && !search.isPending && (
        <div className="mt-6">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm text-gray-500">
              {search.data.total_results} result
              {search.data.total_results !== 1 ? "s" : ""} for{" "}
              <span className="font-mono text-xs text-gray-700">
                {search.data.query_smiles}
              </span>
              {search.data.query_canonical_smiles &&
                search.data.query_canonical_smiles !==
                  search.data.query_smiles && (
                  <span className="ml-2 text-xs text-gray-400">
                    (canonical: {search.data.query_canonical_smiles})
                  </span>
                )}
            </p>
            <span className="text-xs text-gray-400">
              Model: {search.data.model_used}
            </span>
          </div>

          <DataTable
            value={search.data.results}
            stripedRows
            className="rounded-lg border border-gray-200"
            paginator
            rows={10}
            emptyMessage="No matching compounds found."
          >
            <Column
              field="smiles"
              header="SMILES"
              body={(row: { smiles: string }) => (
                <span className="font-mono text-xs">{row.smiles}</span>
              )}
            />
            <Column
              field="canonical_smiles"
              header="Canonical"
              body={(row: { canonical_smiles?: string | null }) =>
                row.canonical_smiles ? (
                  <span className="font-mono text-xs">
                    {row.canonical_smiles}
                  </span>
                ) : (
                  <span className="text-gray-400">—</span>
                )
              }
            />
            <Column field="extracted_id" header="Extracted ID" />
            <Column
              header="Similarity"
              body={(row: { similarity_score: number }) => {
                const pct = Math.round(row.similarity_score * 100);
                return (
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-16 rounded-full bg-gray-200">
                      <div
                        className="h-2 rounded-full bg-blue-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-600">{pct}%</span>
                  </div>
                );
              }}
              style={{ width: "140px" }}
            />
            <Column
              header="Source"
              body={(
                row: {
                  artifact_id: string;
                  page_id: string;
                  page_index: number;
                  artifact_name?: string | null;
                },
              ) => (
                <div className="flex flex-col gap-1">
                  <Link
                    href={`/${workspace}/documents/${row.artifact_id}`}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    {row.artifact_name ?? "Artifact"}
                  </Link>
                  <Link
                    href={`/${workspace}/documents/${row.artifact_id}/pages/${row.page_id}`}
                    className="text-xs text-gray-400 hover:text-gray-600"
                  >
                    Page {row.page_index}
                  </Link>
                </div>
              )}
            />
            <Column
              field="confidence"
              header="Confidence"
              body={(row: { confidence?: number | null }) =>
                row.confidence != null ? (
                  <Tag
                    value={`${(row.confidence * 100).toFixed(0)}%`}
                    severity={row.confidence >= 0.8 ? "success" : "warning"}
                  />
                ) : (
                  <span className="text-gray-400">—</span>
                )
              }
              style={{ width: "100px" }}
            />
          </DataTable>
        </div>
      )}
    </div>
  );
}
