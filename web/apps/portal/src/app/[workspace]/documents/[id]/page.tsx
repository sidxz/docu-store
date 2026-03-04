"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useRef } from "react";
import { Button } from "primereact/button";
import { Card } from "primereact/card";
import { Column } from "primereact/column";
import { ConfirmDialog, confirmDialog } from "primereact/confirmdialog";
import { DataTable } from "primereact/datatable";
import { ProgressSpinner } from "primereact/progressspinner";
import { Tag } from "primereact/tag";
import { Toast } from "primereact/toast";

import type { components } from "@docu-store/api-client";
import { WorkflowStatusBadge } from "@/components/WorkflowStatusBadge";
import {
  useArtifact,
  useArtifactWorkflows,
  useDeleteArtifact,
} from "@/hooks/use-artifacts";

type PageResponse = components["schemas"]["PageResponse"];

/** Shape of the workflow endpoint response (untyped in OpenAPI schema) */
interface WorkflowMap {
  workflows?: Record<string, { workflow_id: string; status: string }>;
}

export default function ArtifactDetailPage() {
  const { workspace, id } = useParams<{ workspace: string; id: string }>();
  const router = useRouter();
  const toast = useRef<Toast>(null);
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

  const handleDelete = () => {
    confirmDialog({
      message: "Delete this artifact and all its pages?",
      header: "Confirm Deletion",
      icon: "pi pi-exclamation-triangle",
      acceptClassName: "p-button-danger",
      accept: async () => {
        try {
          await deleteMutation.mutateAsync(id);
          router.push(`/${workspace}/documents`);
        } catch {
          toast.current?.show({
            severity: "error",
            summary: "Delete failed",
            detail: "Could not delete the artifact. Please try again.",
          });
        }
      },
    });
  };

  const workflowMap = (workflowData as WorkflowMap | undefined)?.workflows;
  const workflows = workflowMap
    ? Object.entries(workflowMap).map(([name, info]) => ({ name, ...info }))
    : undefined;

  return (
    <div className="p-6">
      <Toast ref={toast} />
      <ConfirmDialog />

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
            value={pages as PageResponse[]}
            stripedRows
            className="rounded-lg border border-gray-200"
            emptyMessage="No pages."
          >
            <Column
              header="Name"
              body={(row: PageResponse) => (
                <Link
                  href={`/${workspace}/documents/${id}/pages/${row.page_id}`}
                  className="text-blue-600 hover:underline"
                >
                  {row.name ?? `Page ${row.index}`}
                </Link>
              )}
            />
            <Column field="index" header="Index" style={{ width: "80px" }} />
            <Column
              header="Text"
              body={(row: PageResponse) => {
                const text = row.text_mention?.text;
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
              body={(row: PageResponse) => row.compound_mentions?.length ?? 0}
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
