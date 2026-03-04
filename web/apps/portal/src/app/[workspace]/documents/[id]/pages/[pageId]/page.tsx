"use client";

import { useParams, useRouter } from "next/navigation";
import { Button } from "primereact/button";
import { Card } from "primereact/card";
import { Column } from "primereact/column";
import { DataTable } from "primereact/datatable";
import { ProgressSpinner } from "primereact/progressspinner";
import { Tag } from "primereact/tag";

import { WorkflowStatusBadge } from "@/components/WorkflowStatusBadge";
import { usePage, usePageWorkflows } from "@/hooks/use-pages";

export default function PageViewerPage() {
  const { workspace, id, pageId } = useParams<{
    workspace: string;
    id: string;
    pageId: string;
  }>();
  const router = useRouter();
  const { data: page, isLoading, error } = usePage(pageId);
  const { data: workflowData } = usePageWorkflows(pageId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <ProgressSpinner />
      </div>
    );
  }

  if (error || !page) {
    return (
      <div className="p-6">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          Failed to load page.
        </div>
        <Button
          label="Back to Artifact"
          icon="pi pi-arrow-left"
          severity="secondary"
          text
          className="mt-4"
          onClick={() => router.push(`/${workspace}/documents/${id}`)}
        />
      </div>
    );
  }

  const workflowMap = (
    workflowData as {
      workflows?: Record<string, { workflow_id: string; status: string }>;
    } | undefined
  )?.workflows;
  const workflows = workflowMap
    ? Object.entries(workflowMap).map(([name, info]) => ({ name, ...info }))
    : undefined;

  return (
    <div className="p-6">
      {/* Header */}
      <Button
        label="Back to Artifact"
        icon="pi pi-arrow-left"
        severity="secondary"
        text
        size="small"
        className="mb-4"
        onClick={() => router.push(`/${workspace}/documents/${id}`)}
      />
      <h1 className="text-2xl font-semibold text-gray-900">{page.name}</h1>
      <p className="mt-1 text-sm text-gray-500">
        Page index: {page.index} | ID:{" "}
        <span className="font-mono">{pageId}</span>
      </p>

      {/* Two-column layout: text + compounds */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Extracted text */}
        <div>
          <h2 className="mb-2 text-sm font-medium text-gray-700">
            Extracted Text
          </h2>
          <Card className="shadow-sm">
            {page.text_mention?.text ? (
              <div className="max-h-96 overflow-y-auto text-sm leading-relaxed text-gray-700 whitespace-pre-wrap">
                {page.text_mention.text}
              </div>
            ) : (
              <p className="text-gray-400">No text extracted yet.</p>
            )}
            {page.text_mention?.model_name && (
              <div className="mt-3 border-t border-gray-100 pt-2 text-xs text-gray-400">
                Model: {page.text_mention.model_name}
                {page.text_mention.confidence != null &&
                  ` | Confidence: ${(page.text_mention.confidence * 100).toFixed(0)}%`}
              </div>
            )}
          </Card>
        </div>

        {/* Summary */}
        <div>
          <h2 className="mb-2 text-sm font-medium text-gray-700">Summary</h2>
          <Card className="shadow-sm">
            {page.summary_candidate?.summary ? (
              <div className="text-sm leading-relaxed text-gray-700">
                {page.summary_candidate.summary}
              </div>
            ) : (
              <p className="text-gray-400">No summary generated yet.</p>
            )}
            {page.summary_candidate?.model_name && (
              <div className="mt-3 border-t border-gray-100 pt-2 text-xs text-gray-400">
                Model: {page.summary_candidate.model_name}
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Tag mentions */}
      {page.tag_mentions && page.tag_mentions.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-2 text-sm font-medium text-gray-700">
            Tag Mentions
          </h2>
          <div className="flex flex-wrap gap-2">
            {page.tag_mentions.map((tm, i) => (
              <Tag
                key={`${tm.tag}-${i}`}
                value={tm.tag}
                severity={
                  tm.entity_type === "compound_name"
                    ? "success"
                    : tm.entity_type === "target"
                      ? "warning"
                      : "secondary"
                }
              />
            ))}
          </div>
        </div>
      )}

      {/* Compound mentions */}
      {page.compound_mentions && page.compound_mentions.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-2 text-sm font-medium text-gray-700">
            Compound Mentions ({page.compound_mentions.length})
          </h2>
          <DataTable
            value={page.compound_mentions}
            stripedRows
            className="rounded-lg border border-gray-200"
            paginator
            rows={10}
          >
            <Column
              field="smiles"
              header="SMILES"
              body={(row: { smiles: string }) => (
                <span className="font-mono text-xs">{row.smiles}</span>
              )}
            />
            <Column field="canonical_smiles" header="Canonical" />
            <Column
              field="is_smiles_valid"
              header="Valid"
              body={(row: { is_smiles_valid?: boolean | null }) =>
                row.is_smiles_valid === true ? (
                  <Tag value="Yes" severity="success" />
                ) : row.is_smiles_valid === false ? (
                  <Tag value="No" severity="danger" />
                ) : (
                  <span className="text-gray-400">—</span>
                )
              }
              style={{ width: "80px" }}
            />
            <Column field="extracted_id" header="Extracted ID" />
            <Column
              field="confidence"
              header="Confidence"
              body={(row: { confidence?: number | null }) =>
                row.confidence != null
                  ? `${(row.confidence * 100).toFixed(0)}%`
                  : "—"
              }
              style={{ width: "100px" }}
            />
          </DataTable>
        </div>
      )}

      {/* Workflows */}
      {workflows && workflows.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-2 text-sm font-medium text-gray-700">Workflows</h2>
          <div className="flex flex-wrap gap-3">
            {workflows.map((w) => (
              <div
                key={w.name}
                className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2"
              >
                <span className="text-xs text-gray-600">
                  {w.name.replace(/_/g, " ")}
                </span>
                <WorkflowStatusBadge status={w.status} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
