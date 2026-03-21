"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import { Button } from "primereact/button";
import { ConfirmDialog, confirmDialog } from "primereact/confirmdialog";
import { Message } from "primereact/message";
import { TabPanel, TabView } from "primereact/tabview";
import { Toast } from "primereact/toast";
import { FileText, ArrowLeft, Lock, Users, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";

import { PageHeader } from "@/components/ui/PageHeader";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { OverviewTab } from "@/components/documents/OverviewTab";
import { PagesTab } from "@/components/documents/PagesTab";
import { PdfEmbed } from "@/components/PdfEmbed";
import { WorkflowList, parseWorkflows } from "@/components/WorkflowList";
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
import { authFetch } from "@/lib/auth-fetch";
import { getErrorMessage } from "@/lib/api-error";

export default function ArtifactDetailPage() {
  const { workspace, id } = useParams<{ workspace: string; id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useRef<Toast>(null);

  const TAB_KEYS = ["overview", "pages", "pdf", "workflows"] as const;
  const tabParam = searchParams.get("tab");
  const activeTab = Math.max(0, TAB_KEYS.indexOf(tabParam as typeof TAB_KEYS[number]));

  const handleTabChange = (index: number) => {
    const key = TAB_KEYS[index] ?? "overview";
    const sp = new URLSearchParams(searchParams.toString());
    if (key === "overview") {
      sp.delete("tab");
    } else {
      sp.set("tab", key);
    }
    const qs = sp.toString();
    router.replace(`/${workspace}/documents/${id}${qs ? `?${qs}` : ""}`, { scroll: false });
  };
  const { user } = useSession();
  const { data: artifact, isLoading, error } = useArtifact(id);
  const { data: workflowData } = useArtifactWorkflows(id);
  const { data: acl } = useArtifactPermissions(id);
  const deleteMutation = useDeleteArtifact();
  const rerunMutation = useRerunArtifactWorkflow(id);

  // Record document open for activity tracking (fire-and-forget)
  useEffect(() => {
    if (artifact) {
      authFetch("/user/activity/document", {
        method: "POST",
        body: JSON.stringify({
          artifact_id: artifact.artifact_id,
          artifact_title: artifact.title_mention?.title ?? artifact.source_filename ?? null,
        }),
        headers: { "Content-Type": "application/json" },
      }).catch(() => {});
    }
  }, [artifact?.artifact_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const isOwnerOrAdmin =
    !!artifact?.owner_id && artifact.owner_id === user.id;

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (error || !artifact) {
    return (
      <div>
        <Message
          severity="error"
          text={getErrorMessage(error)}
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

  const workflows = parseWorkflows(workflowData);

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

      {/* Workflow status banner */}
      {workflows && (() => {
        const running = workflows.filter((w) => w.status === "RUNNING");
        const failed = workflows.filter((w) => w.status === "FAILED" || w.status === "TIMED_OUT");
        const allDone = workflows.every((w) => w.status === "COMPLETED" || w.status === "NOT_FOUND");

        if (running.length > 0) {
          return (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-blue-500/20 bg-blue-500/5 px-4 py-2.5">
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-blue-500" />
              <div className="min-w-0 text-sm">
                <span className="font-medium text-blue-400">
                  {running.length} {running.length === 1 ? "workflow" : "workflows"} running
                </span>
                <span className="ml-2 text-xs text-text-muted">
                  {running.map((w) => w.name.replace(/_/g, " ")).join(", ")}
                </span>
              </div>
            </div>
          );
        }

        if (failed.length > 0) {
          return (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-2.5">
              <AlertCircle className="h-4 w-4 shrink-0 text-red-500" />
              <div className="min-w-0 text-sm">
                <span className="font-medium text-red-400">
                  {failed.length} {failed.length === 1 ? "workflow" : "workflows"} failed
                </span>
                <span className="ml-2 text-xs text-text-muted">
                  {failed.map((w) => w.name.replace(/_/g, " ")).join(", ")}
                </span>
              </div>
            </div>
          );
        }

        return null;
      })()}

      <TabView className="mt-2" activeIndex={activeTab} onTabChange={(e) => handleTabChange(e.index)}>
        {/* Overview Tab */}
        <TabPanel header="Overview">
          <OverviewTab
            artifact={artifact}
            workspace={workspace}
            artifactId={id}
          />
        </TabPanel>

        {/* Pages Tab */}
        <TabPanel header="Pages">
          <PagesTab
            pages={pages}
            workspace={workspace}
            artifactId={id}
          />
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
            <WorkflowList
              workflows={workflows}
              rerunableWorkflows={RERUNNABLE_ARTIFACT_WORKFLOWS}
              onRerun={(name) => rerunMutation.mutateAsync(name)}
              isRerunning={rerunMutation.isPending}
              rerunningName={rerunMutation.variables}
              variant="cards"
            />
          </div>
        </TabPanel>
      </TabView>
    </div>
  );
}
