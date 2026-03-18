"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useRef } from "react";
import { Button } from "primereact/button";
import { Column } from "primereact/column";
import { ConfirmDialog, confirmDialog } from "primereact/confirmdialog";
import { DataTable } from "primereact/datatable";
import { Message } from "primereact/message";
import { ProgressSpinner } from "primereact/progressspinner";
import { TabPanel, TabView } from "primereact/tabview";
import { Tag } from "primereact/tag";
import { Toast } from "primereact/toast";
import { FileText, ArrowLeft, CheckCircle2 } from "lucide-react";

import type { components } from "@docu-store/api-client";
import type { WorkflowMap } from "@docu-store/types";
import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { WorkflowStatusBadge } from "@/components/WorkflowStatusBadge";
import {
  useArtifact,
  useArtifactWorkflows,
  useDeleteArtifact,
  useRerunArtifactWorkflow,
  RERUNNABLE_ARTIFACT_WORKFLOWS,
} from "@/hooks/use-artifacts";
import { ShareDialog } from "@/components/sharing/ShareDialog";
import { useSession } from "@/lib/auth";
import { API_URL } from "@/lib/constants";

type PageResponse = components["schemas"]["PageResponse"];

function PdfEmbed({ artifactId }: { artifactId: string }) {
  const { blobUrl, error } = useAuthBlobUrl(
    `${API_URL}/artifacts/${artifactId}/pdf`,
  );

  if (error) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-ds-error/20 bg-ds-error/5">
        <p className="text-sm text-ds-error">Failed to load PDF</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border-default">
      {!blobUrl && (
        <div className="h-[80vh] w-full animate-pulse bg-surface-elevated" />
      )}
      {blobUrl && (
        <iframe
          src={blobUrl}
          className="h-[80vh] w-full"
          title="PDF Viewer"
        />
      )}
    </div>
  );
}

export default function ArtifactDetailPage() {
  const { workspace, id } = useParams<{ workspace: string; id: string }>();
  const router = useRouter();
  const toast = useRef<Toast>(null);
  const { user } = useSession();
  const { data: artifact, isLoading, error } = useArtifact(id);
  const { data: workflowData } = useArtifactWorkflows(id);
  const deleteMutation = useDeleteArtifact();
  const rerunMutation = useRerunArtifactWorkflow(id);

  const isOwnerOrAdmin =
    !!artifact?.owner_id && artifact.owner_id === user.id;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <ProgressSpinner
          style={{ width: "2rem", height: "2rem" }}
          strokeWidth="3"
        />
      </div>
    );
  }

  if (error || !artifact) {
    return (
      <div>
        <Message
          severity="error"
          text="Failed to load artifact. It may not exist or the backend is unreachable."
        />
        <Button
          label="Back to Documents"
          icon={<ArrowLeft className="h-4 w-4" />}
          onClick={() => router.push(`/${workspace}/documents`)}
          text
          severity="secondary"
          size="small"
          className="mt-4"
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
    <div>
      <Toast ref={toast} />
      <ConfirmDialog />

      {/* Back link */}
      <Button
        label="Documents"
        icon={<ArrowLeft className="h-3.5 w-3.5" />}
        onClick={() => router.push(`/${workspace}/documents`)}
        text
        severity="secondary"
        size="small"
        className="mb-4"
      />

      <PageHeader
        icon={FileText}
        title={title}
        subtitle={`${artifact.artifact_type.replace(/_/g, " ")} · ${pages.length} pages`}
        actions={
          <div className="flex items-center gap-2">
            <ShareDialog
              artifactId={id}
              isOwnerOrAdmin={isOwnerOrAdmin}
            />
            <Button
              label="Delete"
              icon="pi pi-trash"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
              loading={deleteMutation.isPending}
              severity="danger"
              outlined
              size="small"
            />
          </div>
        }
      />

      <TabView className="mt-2">
        {/* PDF Tab */}
        <TabPanel header="PDF">
          <div className="pt-4">
            <PdfEmbed artifactId={id} />
          </div>
        </TabPanel>

        {/* Overview Tab */}
        <TabPanel header="Overview">
          <div className="space-y-6 pt-4">
            {/* Metadata */}
            <Card>
              <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
                <div>
                  <span className="text-text-muted">Type</span>
                  <p className="mt-1 font-medium text-text-primary">
                    {artifact.artifact_type.replace(/_/g, " ")}
                  </p>
                </div>
                <div>
                  <span className="text-text-muted">MIME Type</span>
                  <p className="mt-1 font-mono text-text-primary">
                    {artifact.mime_type}
                  </p>
                </div>
                <div>
                  <span className="text-text-muted">Pages</span>
                  <p className="mt-1 font-medium text-text-primary">
                    {pages.length}
                  </p>
                </div>
                <div>
                  <span className="text-text-muted">Source</span>
                  <p className="mt-1 truncate text-text-primary">
                    {artifact.source_uri || "—"}
                  </p>
                </div>
              </div>
            </Card>

            {/* Tags */}
            {artifact.tags && artifact.tags.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-medium text-text-secondary">
                  Tags
                </h3>
                <div className="flex flex-wrap gap-2">
                  {artifact.tags.map((tag) => (
                    <Tag key={tag} value={tag} severity="secondary" rounded />
                  ))}
                </div>
              </div>
            )}

            {/* Summary */}
            {artifact.summary_candidate?.summary && (
              <Card>
                <h3 className="mb-3 text-sm font-medium text-text-secondary">
                  Summary
                </h3>
                <p className="text-sm leading-relaxed text-text-primary">
                  {artifact.summary_candidate.summary}
                </p>
                {artifact.summary_candidate.model_name && (
                  <p className="mt-3 border-t border-border-subtle pt-2 text-xs text-text-muted">
                    Generated by {artifact.summary_candidate.model_name}
                  </p>
                )}
              </Card>
            )}
          </div>
        </TabPanel>

        {/* Pages Tab */}
        <TabPanel header="Pages">
          <div className="pt-4">
            {isPageObjects ? (
              <DataTable
                value={pages as PageResponse[]}
                className="rounded-xl border border-border-default"
                emptyMessage="No pages."
                rowHover
              >
                <Column
                  header="Name"
                  body={(row: PageResponse) => (
                    <Link
                      href={`/${workspace}/documents/${id}/pages/${row.page_id}`}
                      className="font-medium text-accent-text hover:underline"
                    >
                      {row.name ?? `Page ${row.index}`}
                    </Link>
                  )}
                />
                <Column
                  field="index"
                  header="Index"
                  style={{ width: "80px" }}
                />
                <Column
                  header="Text"
                  body={(row: PageResponse) => {
                    const text = row.text_mention?.text;
                    return text ? (
                      <span className="block max-w-md truncate text-sm text-text-secondary">
                        {text.slice(0, 120)}...
                      </span>
                    ) : (
                      <span className="text-text-muted">—</span>
                    );
                  }}
                />
                <Column
                  header="Compounds"
                  body={(row: PageResponse) => row.compound_mentions?.length ?? 0}
                  style={{ width: "100px" }}
                />
                <Column
                  header="Summary"
                  body={(row: PageResponse) =>
                    row.summary_candidate?.summary ? (
                      <CheckCircle2 className="h-4 w-4 text-ds-success" />
                    ) : (
                      <span className="text-text-muted">—</span>
                    )
                  }
                  style={{ width: "80px" }}
                />
              </DataTable>
            ) : (
              <DataTable
                value={(pages as string[]).map((pageId, idx) => ({
                  page_id: pageId,
                  index: idx,
                }))}
                className="rounded-xl border border-border-default"
                emptyMessage="No pages."
                rowHover
              >
                <Column
                  header="Page"
                  body={(row: { page_id: string; index: number }) => (
                    <Link
                      href={`/${workspace}/documents/${id}/pages/${row.page_id}`}
                      className="font-mono text-sm text-accent-text hover:underline"
                    >
                      {row.page_id}
                    </Link>
                  )}
                />
                <Column
                  field="index"
                  header="Index"
                  style={{ width: "80px" }}
                />
              </DataTable>
            )}
          </div>
        </TabPanel>

        {/* Workflows Tab */}
        <TabPanel header="Workflows">
          <div className="pt-4">
            {workflows && workflows.length > 0 ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {workflows.map((w) => (
                  <Card key={w.name}>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-text-primary">
                        {w.name.replace(/_/g, " ")}
                      </span>
                      <div className="flex items-center gap-2">
                        <WorkflowStatusBadge status={w.status} />
                        {RERUNNABLE_ARTIFACT_WORKFLOWS.has(w.name) &&
                          w.status !== "RUNNING" && (
                            <Button
                              icon="pi pi-replay"
                              onClick={async () => {
                                try {
                                  await rerunMutation.mutateAsync(w.name);
                                } catch {
                                  toast.current?.show({
                                    severity: "error",
                                    summary: "Rerun failed",
                                    detail: `Could not rerun ${w.name.replace(/_/g, " ")}`,
                                    life: 5000,
                                  });
                                }
                              }}
                              loading={
                                rerunMutation.isPending &&
                                rerunMutation.variables === w.name
                              }
                              disabled={rerunMutation.isPending}
                              text
                              severity="secondary"
                              size="small"
                              rounded
                              tooltip="Rerun"
                              tooltipOptions={{ position: "top" }}
                            />
                          )}
                      </div>
                    </div>
                    <p className="mt-2 truncate font-mono text-xs text-text-muted">
                      {w.workflow_id}
                    </p>
                  </Card>
                ))}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-text-muted">
                No workflows found for this artifact.
              </p>
            )}
          </div>
        </TabPanel>
      </TabView>
    </div>
  );
}
