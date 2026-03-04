"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Button } from "primereact/button";
import { Card } from "primereact/card";
import { Column } from "primereact/column";
import { DataTable } from "primereact/datatable";
import { ProgressSpinner } from "primereact/progressspinner";
import { Tag } from "primereact/tag";

import { WorkflowStatusBadge } from "@/components/WorkflowStatusBadge";
import {
  useArtifact,
  useArtifactWorkflows,
  useDeleteArtifact,
} from "@/hooks/use-artifacts";

export default function ArtifactDetailPage() {
  const { workspace, id } = useParams<{ workspace: string; id: string }>();
  const router = useRouter();
  const { data: artifact, isLoading, error } = useArtifact(id);
  const { data: workflowData } = useArtifactWorkflows(id);
  const deleteMutation = useDeleteArtifact();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <ProgressSpinner />
      </div>
    );
  }

  if (error || !artifact) {
    return (
      <div className="p-6">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          Failed to load artifact. It may not exist or the backend is
          unreachable.
        </div>
        <Button
          label="Back to Documents"
          icon="pi pi-arrow-left"
          severity="secondary"
          text
          className="mt-4"
          onClick={() => router.push(`/${workspace}/documents`)}
        />
      </div>
    );
  }

  const title =
    artifact.title_mention?.title ??
    artifact.source_filename ??
    "Untitled";

  const pages = artifact.pages ?? [];
  const isPageObjects = pages.length > 0 && typeof pages[0] === "object";

  const handleDelete = async () => {
    if (!confirm("Delete this artifact and all its pages?")) return;
    await deleteMutation.mutateAsync(id);
    router.push(`/${workspace}/documents`);
  };

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
      <div className="mb-6 flex items-start justify-between">
        <div>
          <Button
            label="Back"
            icon="pi pi-arrow-left"
            severity="secondary"
            text
            size="small"
            className="mb-2"
            onClick={() => router.push(`/${workspace}/documents`)}
          />
          <h1 className="text-2xl font-semibold text-gray-900">{title}</h1>
          <p className="mt-1 text-sm text-gray-500 font-mono">{id}</p>
        </div>
        <Button
          icon="pi pi-trash"
          severity="danger"
          text
          onClick={handleDelete}
          loading={deleteMutation.isPending}
        />
      </div>

      {/* Metadata cards */}
      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card className="shadow-sm">
          <div className="text-sm text-gray-500">Type</div>
          <div className="mt-1">
            <Tag value={artifact.artifact_type} severity="info" />
          </div>
        </Card>
        <Card className="shadow-sm">
          <div className="text-sm text-gray-500">MIME Type</div>
          <div className="mt-1 text-sm font-mono">{artifact.mime_type}</div>
        </Card>
        <Card className="shadow-sm">
          <div className="text-sm text-gray-500">Pages</div>
          <div className="mt-1 text-lg font-semibold">{pages.length}</div>
        </Card>
      </div>

      {/* Tags */}
      {artifact.tags && artifact.tags.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-medium text-gray-700">Tags</h2>
          <div className="flex flex-wrap gap-2">
            {artifact.tags.map((tag) => (
              <Tag key={tag} value={tag} severity="secondary" />
            ))}
          </div>
        </div>
      )}

      {/* Summary */}
      {artifact.summary_candidate?.summary && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-medium text-gray-700">Summary</h2>
          <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-700 leading-relaxed">
            {artifact.summary_candidate.summary}
          </div>
        </div>
      )}

      {/* Workflows */}
      {workflows && workflows.length > 0 && (
        <div className="mb-6">
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

      {/* Pages list */}
      <div>
        <h2 className="mb-2 text-sm font-medium text-gray-700">Pages</h2>
        {isPageObjects ? (
          <DataTable
            value={pages as Record<string, unknown>[]}
            stripedRows
            className="rounded-lg border border-gray-200"
            emptyMessage="No pages."
          >
            <Column
              header="Name"
              body={(row: Record<string, unknown>) => (
                <Link
                  href={`/${workspace}/documents/${id}/pages/${row.page_id}`}
                  className="text-blue-600 hover:underline"
                >
                  {(row.name as string) ?? `Page ${row.index}`}
                </Link>
              )}
            />
            <Column field="index" header="Index" style={{ width: "80px" }} />
            <Column
              header="Text"
              body={(row: Record<string, unknown>) => {
                const text = (row.text_mention as { text?: string } | null)?.text;
                return text ? (
                  <span className="text-sm text-gray-600 truncate block max-w-md">
                    {text.slice(0, 120)}...
                  </span>
                ) : (
                  <span className="text-gray-400">—</span>
                );
              }}
            />
            <Column
              header="Compounds"
              body={(row: Record<string, unknown>) => {
                const compounds = row.compound_mentions as unknown[] | undefined;
                return compounds?.length ?? 0;
              }}
              style={{ width: "100px" }}
            />
          </DataTable>
        ) : (
          <DataTable
            value={(pages as string[]).map((pageId, idx) => ({
              page_id: pageId,
              index: idx,
            }))}
            stripedRows
            className="rounded-lg border border-gray-200"
            emptyMessage="No pages."
          >
            <Column
              header="Page"
              body={(row: { page_id: string; index: number }) => (
                <Link
                  href={`/${workspace}/documents/${id}/pages/${row.page_id}`}
                  className="text-blue-600 hover:underline font-mono text-sm"
                >
                  {row.page_id}
                </Link>
              )}
            />
            <Column field="index" header="Index" style={{ width: "80px" }} />
          </DataTable>
        )}
      </div>
    </div>
  );
}
