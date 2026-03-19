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
import { FileText, ArrowLeft, CheckCircle2, Users, Calendar, Lock, Globe } from "lucide-react";

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
import { useArtifactPermissions } from "@/hooks/use-permissions";
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
  const { data: acl } = useArtifactPermissions(id);
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
        className="mb-4"
      />

      <PageHeader
        icon={FileText}
        title={title}
        subtitle={`${artifact.artifact_type.replace(/_/g, " ")} · ${pages.length} pages`}
        badge={
          acl?.visibility === "private" && acl.shares?.length > 0 ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-accent-light px-1.5 py-0.5 text-xs font-medium text-accent-text" title="Shared with specific people">
              <Users className="size-3" />
              Shared
            </span>
          ) : acl?.visibility === "private" ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-surface-sunken px-1.5 py-0.5 text-xs font-medium text-text-muted" title="Only you can access">
              <Lock className="size-3" />
              Private
            </span>
          ) : null
        }
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
            />
          </div>
        }
      />

      <TabView className="mt-2">
        {/* Overview Tab */}
        <TabPanel header="Overview">
          <div className="space-y-6 pt-4">
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

            {/* Authors & Date */}
            {(artifact.author_mentions?.length > 0 || artifact.presentation_date) && (
              <Card>
                <div className="space-y-3">
                  {artifact.author_mentions?.length > 0 && (
                    <div className="flex items-start gap-3">
                      <Users className="mt-0.5 h-4 w-4 shrink-0 text-text-muted" />
                      <div>
                        <span className="text-xs font-medium text-text-muted">Authors</span>
                        <div className="mt-1 flex flex-wrap gap-2">
                          {artifact.author_mentions.map((am, i) => (
                            <span
                              key={`${am.name}-${i}`}
                              className="rounded-md border border-border-default bg-surface-elevated px-2 py-1 text-sm font-medium text-text-primary"
                            >
                              {am.name}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                  {artifact.presentation_date && (
                    <div className="flex items-center gap-3">
                      <Calendar className="h-4 w-4 shrink-0 text-text-muted" />
                      <div>
                        <span className="text-xs font-medium text-text-muted">Date</span>
                        <p className="mt-1 text-sm font-medium text-text-primary">
                          {new Date(artifact.presentation_date.date).toLocaleDateString(undefined, {
                            year: "numeric",
                            month: "long",
                            day: "numeric",
                          })}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            )}

            {/* Tag Mentions — grouped by entity type */}
            {artifact.tag_mentions && artifact.tag_mentions.length > 0 && (() => {
              type TagMentionItem = NonNullable<typeof artifact.tag_mentions>[number];
              type Bioactivity = { assay_type: string; value: string; unit: string; raw_text: string };
              const ENTITY_COLORS: Record<string, "success" | "warning" | "danger" | "secondary"> = {
                compound_name: "success",
                target: "warning",
                disease: "danger",
              };
              const compounds: TagMentionItem[] = [];
              const grouped = new Map<string, TagMentionItem[]>();
              for (const tm of artifact.tag_mentions) {
                const key = tm.entity_type ?? "other";
                if (key === "compound_name") {
                  compounds.push(tm);
                } else {
                  const arr = grouped.get(key);
                  if (arr) arr.push(tm);
                  else grouped.set(key, [tm]);
                }
              }
              return (
                <div>
                  <h3 className="mb-3 text-sm font-medium text-text-secondary">
                    Tag Mentions
                  </h3>
                  <div className="space-y-3">
                    {compounds.length > 0 && (
                      <div className="flex items-start gap-3">
                        <span className="mt-0.5 min-w-[120px] shrink-0 text-xs font-medium text-text-muted">
                          compound name
                        </span>
                        <div className="flex flex-wrap gap-2">
                          {compounds.map((tm, i) => {
                            const params = tm.additional_model_params as Record<string, unknown> | undefined;
                            const activities = params?.bioactivities as Bioactivity[] | undefined;
                            const synonyms = params?.synonyms as string | undefined;
                            return (
                              <div
                                key={`${tm.tag}-${i}`}
                                className="rounded-lg border border-border-default bg-surface-elevated px-3 py-2"
                              >
                                <div className="flex items-center gap-2">
                                  <Tag value={tm.tag} severity="success" rounded />
                                  {synonyms && (
                                    <span className="text-xs text-text-muted">
                                      aka {synonyms}
                                    </span>
                                  )}
                                </div>
                                {activities && activities.length > 0 && (
                                  <table className="mt-2 w-full text-xs">
                                    <thead>
                                      <tr className="border-b border-border-subtle text-text-muted">
                                        <th className="pb-1 pr-3 text-left font-medium">Assay</th>
                                        <th className="pb-1 pr-3 text-left font-medium">Value</th>
                                        <th className="pb-1 text-left font-medium">Source</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {activities.map((a, j) => (
                                        <tr key={j} className="border-b border-border-subtle last:border-0">
                                          <td className="py-1 pr-3 font-mono font-medium text-text-primary">
                                            {a.assay_type}
                                          </td>
                                          <td className="py-1 pr-3 font-mono text-text-primary">
                                            {a.value}{a.unit ? ` ${a.unit}` : ""}
                                          </td>
                                          <td className="py-1 text-text-muted">
                                            {a.raw_text}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                    {[...grouped.entries()].map(([entityType, tags]) => (
                      <div key={entityType} className="flex items-start gap-3">
                        <span className="mt-0.5 min-w-[120px] shrink-0 text-xs font-medium text-text-muted">
                          {entityType.replace(/_/g, " ")}
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {tags.map((tm, i) => (
                            <Tag
                              key={`${tm.tag}-${i}`}
                              value={tm.tag}
                              severity={ENTITY_COLORS[entityType] ?? "secondary"}
                              rounded
                            />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}

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
                  header="Summary"
                  body={(row: PageResponse) => {
                    const summary = row.summary_candidate?.summary;
                    return summary ? (
                      <span className="block max-w-md truncate text-sm text-text-secondary">
                        {summary.slice(0, 120)}
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

        {/* PDF Tab */}
        <TabPanel header="PDF">
          <div className="pt-4">
            <PdfEmbed artifactId={id} />
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
