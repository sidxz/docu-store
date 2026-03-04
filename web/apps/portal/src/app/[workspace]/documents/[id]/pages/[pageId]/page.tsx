"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Image,
  FileText,
} from "lucide-react";

import { MoleculeStructure } from "@docu-store/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { WorkflowStatusBadge } from "@/components/WorkflowStatusBadge";
import { useArtifact } from "@/hooks/use-artifacts";
import { usePage, usePageWorkflows } from "@/hooks/use-pages";

const ENTITY_TYPE_COLORS: Record<string, string> = {
  compound_name: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
  target: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
  disease: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400",
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function PageImage({
  artifactId,
  pageIndex,
}: {
  artifactId: string;
  pageIndex: number;
}) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  return (
    <div className="flex justify-center">
      {!loaded && !error && (
        <div className="h-[600px] w-full animate-pulse rounded-lg bg-surface-elevated" />
      )}
      {error ? (
        <div className="flex h-48 w-full items-center justify-center rounded-lg border border-border-default bg-surface-elevated">
          <p className="text-sm text-text-muted">Page image not available</p>
        </div>
      ) : (
        <img
          src={`${API_URL}/artifacts/${artifactId}/pages/${pageIndex}/image`}
          alt={`Page ${pageIndex + 1}`}
          className={`max-h-[80vh] rounded-lg border border-border-default object-contain ${loaded ? "" : "hidden"}`}
          onLoad={() => setLoaded(true)}
          onError={() => {
            setError(true);
            setLoaded(true);
          }}
        />
      )}
    </div>
  );
}

function PagePdfEmbed({
  artifactId,
  pageNumber,
}: {
  artifactId: string;
  pageNumber: number;
}) {
  const [loaded, setLoaded] = useState(false);

  return (
    <div className="overflow-hidden rounded-lg border border-border-default">
      {!loaded && (
        <div className="h-[80vh] w-full animate-pulse bg-surface-elevated" />
      )}
      <iframe
        src={`${API_URL}/artifacts/${artifactId}/pdf#page=${pageNumber}`}
        className={`h-[80vh] w-full ${loaded ? "" : "hidden"}`}
        title={`PDF page ${pageNumber}`}
        onLoad={() => setLoaded(true)}
      />
    </div>
  );
}

export default function PageViewerPage() {
  const { workspace, id, pageId } = useParams<{
    workspace: string;
    id: string;
    pageId: string;
  }>();
  const router = useRouter();
  const [viewMode, setViewMode] = useState<"image" | "pdf">("image");
  const { data: page, isLoading, error } = usePage(pageId);
  const { data: artifact } = useArtifact(id);
  const { data: workflowData } = usePageWorkflows(pageId);

  // Derive prev/next page IDs from the artifact's page list
  const siblingPages = (() => {
    if (!artifact?.pages || !page) return { prev: null, next: null };
    const pages = artifact.pages;
    const currentIndex = page.index;
    let prevId: string | null = null;
    let nextId: string | null = null;

    for (let i = 0; i < pages.length; i++) {
      const p = pages[i];
      if (typeof p === "string") {
        // pages is list[UUID] — ordered by index
        if (i === currentIndex - 1) prevId = p;
        if (i === currentIndex + 1) nextId = p;
      } else {
        // pages is list[PageResponse]
        if (p.index === currentIndex - 1) prevId = p.page_id;
        if (p.index === currentIndex + 1) nextId = p.page_id;
      }
    }
    return { prev: prevId, next: nextId };
  })();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-accent" />
      </div>
    );
  }

  if (error || !page) {
    return (
      <div>
        <div className="rounded-lg border border-ds-error/20 bg-ds-error/5 p-4 text-ds-error">
          Failed to load page.
        </div>
        <button
          className="mt-4 flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary"
          onClick={() => router.push(`/${workspace}/documents/${id}`)}
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Artifact
        </button>
      </div>
    );
  }

  const workflowMap = (
    workflowData as
      | { workflows?: Record<string, { workflow_id: string; status: string }> }
      | undefined
  )?.workflows;
  const workflows = workflowMap
    ? Object.entries(workflowMap).map(([name, info]) => ({ name, ...info }))
    : undefined;

  return (
    <div>
      {/* Back link */}
      <button
        className="mb-4 flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary transition-colors"
        onClick={() => router.push(`/${workspace}/documents/${id}`)}
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to document
      </button>

      <PageHeader
        icon={BookOpen}
        title={page.name}
        subtitle={`Page ${page.index + 1} · ${page.compound_mentions?.length ?? 0} compounds`}
        actions={
          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={!siblingPages.prev}
              onClick={() =>
                siblingPages.prev &&
                router.push(
                  `/${workspace}/documents/${id}/pages/${siblingPages.prev}`,
                )
              }
              className="flex items-center gap-1 rounded-lg border border-border-default px-2.5 py-1.5 text-sm text-text-secondary transition-colors hover:bg-surface-elevated disabled:opacity-30 disabled:pointer-events-none"
            >
              <ChevronLeft className="h-4 w-4" />
              Prev
            </button>
            <button
              type="button"
              disabled={!siblingPages.next}
              onClick={() =>
                siblingPages.next &&
                router.push(
                  `/${workspace}/documents/${id}/pages/${siblingPages.next}`,
                )
              }
              className="flex items-center gap-1 rounded-lg border border-border-default px-2.5 py-1.5 text-sm text-text-secondary transition-colors hover:bg-surface-elevated disabled:opacity-30 disabled:pointer-events-none"
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        }
      />

      {/* Page visual — PNG image or full PDF */}
      <Card className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <CardHeader title="Page View" />
          <div className="flex items-center gap-1 rounded-lg border border-border-default p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("image")}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                viewMode === "image"
                  ? "bg-accent text-white"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              <Image className="h-3.5 w-3.5" />
              Image
            </button>
            <button
              type="button"
              onClick={() => setViewMode("pdf")}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                viewMode === "pdf"
                  ? "bg-accent text-white"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              <FileText className="h-3.5 w-3.5" />
              Full PDF
            </button>
          </div>
        </div>

        {viewMode === "image" ? (
          <PageImage artifactId={id} pageIndex={page.index} />
        ) : (
          <PagePdfEmbed artifactId={id} pageNumber={page.index + 1} />
        )}
      </Card>

      {/* Two-panel: text + summary */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Extracted Text" />
          {page.text_mention?.text ? (
            <div className="max-h-96 overflow-y-auto text-sm leading-relaxed text-text-primary whitespace-pre-wrap">
              {page.text_mention.text}
            </div>
          ) : (
            <p className="text-text-muted">No text extracted yet.</p>
          )}
          {page.text_mention?.model_name && (
            <div className="mt-3 border-t border-border-subtle pt-2 text-xs text-text-muted">
              Model: {page.text_mention.model_name}
              {page.text_mention.confidence != null &&
                ` · Confidence: ${(page.text_mention.confidence * 100).toFixed(0)}%`}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Summary" />
          {page.summary_candidate?.summary ? (
            <div className="text-sm leading-relaxed text-text-primary">
              {page.summary_candidate.summary}
            </div>
          ) : (
            <p className="text-text-muted">No summary generated yet.</p>
          )}
          {page.summary_candidate?.model_name && (
            <div className="mt-3 border-t border-border-subtle pt-2 text-xs text-text-muted">
              Model: {page.summary_candidate.model_name}
            </div>
          )}
        </Card>
      </div>

      {/* Tag mentions */}
      {page.tag_mentions && page.tag_mentions.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-3 text-sm font-medium text-text-secondary">
            Tag Mentions
          </h3>
          <div className="flex flex-wrap gap-2">
            {page.tag_mentions.map((tm, i) => {
              const colorClass =
                ENTITY_TYPE_COLORS[tm.entity_type ?? ""] ??
                "bg-border-subtle text-text-secondary";
              return (
                <span
                  key={`${tm.tag}-${i}`}
                  className={`rounded-md px-2 py-0.5 text-xs font-medium ${colorClass}`}
                >
                  {tm.tag}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Compound mentions — card grid */}
      {page.compound_mentions && page.compound_mentions.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-3 text-sm font-medium text-text-secondary">
            Compound Mentions ({page.compound_mentions.length})
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {page.compound_mentions.map((cm, i) => (
              <Card key={`${cm.smiles}-${i}`}>
                <div className="flex justify-center border-b border-border-subtle pb-3 mb-3">
                  <MoleculeStructure
                    smiles={cm.smiles}
                    width={180}
                    height={120}
                  />
                </div>
                <div className="space-y-1.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-text-muted">SMILES</span>
                    <span className="font-mono text-text-secondary max-w-[180px] truncate">
                      {cm.smiles}
                    </span>
                  </div>
                  {cm.extracted_id && (
                    <div className="flex items-center justify-between">
                      <span className="text-text-muted">ID</span>
                      <span className="font-medium text-text-primary">
                        {cm.extracted_id}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <span className="text-text-muted">Valid</span>
                    {cm.is_smiles_valid === true ? (
                      <span className="text-ds-success">Yes</span>
                    ) : cm.is_smiles_valid === false ? (
                      <span className="text-ds-error">No</span>
                    ) : (
                      <span className="text-text-muted">—</span>
                    )}
                  </div>
                  {cm.confidence != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-text-muted">Confidence</span>
                      <ScoreBadge score={cm.confidence} variant="pill" />
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Workflows */}
      {workflows && workflows.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-3 text-sm font-medium text-text-secondary">
            Workflows
          </h3>
          <div className="flex flex-wrap gap-3">
            {workflows.map((w) => (
              <div
                key={w.name}
                className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-elevated px-3 py-2"
              >
                <span className="text-xs font-medium text-text-primary">
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
