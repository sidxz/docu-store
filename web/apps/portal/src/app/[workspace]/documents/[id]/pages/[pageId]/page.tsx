"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { AlertCircle, ArrowLeft, BookOpen, ChevronLeft, ChevronRight } from "lucide-react";
import { useAuthzHasRole } from "@sentinel-auth/react";

import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { EntityTagPanel } from "@/components/EntityTagPanel";
import { PdfEmbed } from "@/components/PdfEmbed";
import { CompoundGrid } from "@/components/documents/CompoundGrid";
import { ExtractedTextSection } from "@/components/documents/ExtractedTextSection";
import { WorkflowList, parseWorkflows } from "@/components/WorkflowList";
import { useArtifact } from "@/hooks/use-artifacts";
import {
  usePage,
  usePageWorkflows,
  useRerunPageWorkflow,
  RERUNNABLE_PAGE_WORKFLOWS,
} from "@/hooks/use-pages";
import type { CompoundMention, TextMention } from "@docu-store/types";
import { usePlugins } from "@/plugins";
import { usePubChemEnrichments } from "@/plugins/pubchem";
import { getErrorMessage } from "@/lib/api-error";
import { API_URL } from "@/lib/constants";

const VIEW_MODES = [
  { label: "Image", value: "image" as const },
  { label: "Full PDF", value: "pdf" as const },
];

function PageImage({
  artifactId,
  pageIndex,
}: {
  artifactId: string;
  pageIndex: number;
}) {
  const { blobUrl, error } = useAuthBlobUrl(
    `${API_URL}/artifacts/${artifactId}/pages/${pageIndex}/image`,
  );

  return (
    <div className="flex justify-center">
      {!blobUrl && !error && (
        <Skeleton className="h-[600px] w-full rounded-lg bg-surface-elevated" />
      )}
      {error ? (
        <div className="flex h-48 w-full items-center justify-center rounded-lg border border-border-default bg-surface-elevated">
          <p className="text-sm text-text-muted">Page image not available</p>
        </div>
      ) : blobUrl ? (
        <img
          src={blobUrl}
          alt={`Page ${pageIndex + 1}`}
          className="max-h-[80vh] rounded-lg border border-border-default object-contain"
        />
      ) : null}
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
  const rerunMutation = useRerunPageWorkflow(pageId);
  const canEdit = useAuthzHasRole("editor");
  const { isPluginEnabled } = usePlugins();
  const { enrichmentBySmiles } = usePubChemEnrichments(pageId, {
    enabled: isPluginEnabled("pubchem_enrichment"),
  });

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
        if (i === currentIndex - 1) prevId = p;
        if (i === currentIndex + 1) nextId = p;
      } else {
        if (p.index === currentIndex - 1) prevId = p.page_id;
        if (p.index === currentIndex + 1) nextId = p.page_id;
      }
    }
    return { prev: prevId, next: nextId };
  })();

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (error || !page) {
    return (
      <div>
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertDescription>{getErrorMessage(error)}</AlertDescription>
        </Alert>
        <Button
          variant="ghost"
          onClick={() => router.push(`/${workspace}/documents/${id}?tab=pages`)}
          className="mt-4"
        >
          <ArrowLeft className="size-4" />
          Back to Artifact
        </Button>
      </div>
    );
  }

  const workflows = parseWorkflows(workflowData);

  return (
    <div>
      {/* Back link */}
      <Button
        variant="ghost"
        onClick={() => router.push(`/${workspace}/documents/${id}?tab=pages`)}
        className="mb-4"
      >
        <ArrowLeft className="size-3.5" />
        Back to document
      </Button>

      <PageHeader
        icon={BookOpen}
        title={page.name}
        subtitle={`Page ${page.index + 1} · ${page.compound_mentions?.length ?? 0} compounds`}
        actions={
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              disabled={!siblingPages.prev}
              onClick={() =>
                siblingPages.prev &&
                router.push(
                  `/${workspace}/documents/${id}/pages/${siblingPages.prev}`,
                )
              }
            >
              <ChevronLeft className="size-4" />
              Prev
            </Button>
            <Button
              variant="outline"
              disabled={!siblingPages.next}
              onClick={() =>
                siblingPages.next &&
                router.push(
                  `/${workspace}/documents/${id}/pages/${siblingPages.next}`,
                )
              }
            >
              Next
              <ChevronRight className="size-4" />
            </Button>
          </div>
        }
      />

      {/* Page visual — PNG image or full PDF */}
      <Card className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <CardHeader title="Page View" />
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={viewMode}
            onValueChange={(nv) => nv && setViewMode(nv as "image" | "pdf")}
          >
            {VIEW_MODES.map((o) => (
              <ToggleGroupItem key={o.value} value={o.value}>
                {o.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>

        {viewMode === "image" ? (
          <PageImage artifactId={id} pageIndex={page.index} />
        ) : (
          <PdfEmbed artifactId={id} pageNumber={page.index + 1} />
        )}
      </Card>

      {/* Summary */}
      <Card className="mb-6">
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

      {/* Tag mentions — reuse EntityTagPanel (same grouping + bioactivity rendering) */}
      {page.tag_mentions && page.tag_mentions.length > 0 && (
        <div className="mt-6">
          <EntityTagPanel
            tagMentions={page.tag_mentions}
            workspace={workspace}
            artifactId={id}
            compoundMentions={page.compound_mentions ?? []}
          />
        </div>
      )}

      {/* Compound mentions — card grid (editable "Add compound" card needs the section even at 0) */}
      {((page.compound_mentions?.length ?? 0) > 0 || canEdit) && (
        <CompoundGrid
          compounds={(page.compound_mentions as CompoundMention[]) ?? []}
          enrichmentBySmiles={enrichmentBySmiles}
          editable={canEdit}
          pageId={pageId}
          humanCorrection={page.human_corrections?.compound_mentions}
        />
      )}

      {/* Extracted Text — collapsed by default */}
      <ExtractedTextSection textMention={page.text_mention as TextMention | null | undefined} />

      {/* Workflows */}
      {workflows && workflows.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-3 text-sm font-medium text-text-secondary">
            Workflows
          </h3>
          <WorkflowList
            workflows={workflows}
            rerunableWorkflows={RERUNNABLE_PAGE_WORKFLOWS}
            onRerun={(name) => rerunMutation.mutateAsync(name)}
            isRerunning={rerunMutation.isPending}
            rerunningName={rerunMutation.variables}
            variant="chips"
          />
        </div>
      )}
    </div>
  );
}
