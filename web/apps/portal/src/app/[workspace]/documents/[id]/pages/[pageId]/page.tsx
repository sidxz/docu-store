"use client";

import { useParams, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { ArrowLeft, BookOpen } from "lucide-react";
import { Button } from "primereact/button";
import { Message } from "primereact/message";
import { ProgressSpinner } from "primereact/progressspinner";
import { SelectButton } from "primereact/selectbutton";
import { Tag } from "primereact/tag";
import { Toast } from "primereact/toast";

import { MoleculeStructure } from "@docu-store/ui";
import type { WorkflowMap } from "@docu-store/types";
import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { CopySmiles } from "@/components/ui/CopySmiles";
import { WorkflowStatusBadge } from "@/components/WorkflowStatusBadge";
import { useArtifact } from "@/hooks/use-artifacts";
import {
  usePage,
  usePageWorkflows,
  useRerunPageWorkflow,
  RERUNNABLE_PAGE_WORKFLOWS,
} from "@/hooks/use-pages";
import { usePlugins } from "@/plugins";
import { usePubChemEnrichments, PubChemBadge } from "@/plugins/pubchem";
import { API_URL } from "@/lib/constants";

const ENTITY_TYPE_COLORS: Record<string, { severity: "success" | "warning" | "danger" | "secondary" }> = {
  compound_name: { severity: "success" },
  target: { severity: "warning" },
  disease: { severity: "danger" },
};

const VIEW_MODES = [
  { label: "Image", value: "image" as const, icon: "pi pi-image" },
  { label: "Full PDF", value: "pdf" as const, icon: "pi pi-file-pdf" },
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
        <div className="h-[600px] w-full animate-pulse rounded-lg bg-surface-elevated" />
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

function PagePdfEmbed({
  artifactId,
  pageNumber,
}: {
  artifactId: string;
  pageNumber: number;
}) {
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
          src={`${blobUrl}#page=${pageNumber}`}
          className="h-[80vh] w-full"
          title={`PDF page ${pageNumber}`}
        />
      )}
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
  const toast = useRef<Toast>(null);
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
    return (
      <div className="flex items-center justify-center py-20">
        <ProgressSpinner
          style={{ width: "2rem", height: "2rem" }}
          strokeWidth="3"
        />
      </div>
    );
  }

  if (error || !page) {
    return (
      <div>
        <Message
          severity="error"
          text="Failed to load page."
        />
        <Button
          label="Back to Artifact"
          icon={<ArrowLeft className="h-4 w-4" />}
          onClick={() => router.push(`/${workspace}/documents/${id}`)}
          text
          severity="secondary"
          size="small"
          className="mt-4"
        />
      </div>
    );
  }

  const workflowMap = (workflowData as WorkflowMap | undefined)?.workflows;
  const workflows = workflowMap
    ? Object.entries(workflowMap).map(([name, info]) => ({ name, ...info }))
    : undefined;

  return (
    <div>
      <Toast ref={toast} />

      {/* Back link */}
      <Button
        label="Back to document"
        icon={<ArrowLeft className="h-3.5 w-3.5" />}
        onClick={() => router.push(`/${workspace}/documents/${id}`)}
        text
        severity="secondary"
        size="small"
        className="mb-4"
      />

      <PageHeader
        icon={BookOpen}
        title={page.name}
        subtitle={`Page ${page.index + 1} · ${page.compound_mentions?.length ?? 0} compounds`}
        actions={
          <div className="flex items-center gap-1">
            <Button
              label="Prev"
              icon="pi pi-chevron-left"
              disabled={!siblingPages.prev}
              onClick={() =>
                siblingPages.prev &&
                router.push(
                  `/${workspace}/documents/${id}/pages/${siblingPages.prev}`,
                )
              }
              outlined
              severity="secondary"
              size="small"
            />
            <Button
              label="Next"
              icon="pi pi-chevron-right"
              iconPos="right"
              disabled={!siblingPages.next}
              onClick={() =>
                siblingPages.next &&
                router.push(
                  `/${workspace}/documents/${id}/pages/${siblingPages.next}`,
                )
              }
              outlined
              severity="secondary"
              size="small"
            />
          </div>
        }
      />

      {/* Page visual — PNG image or full PDF */}
      <Card className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <CardHeader title="Page View" />
          <SelectButton
            value={viewMode}
            options={VIEW_MODES}
            onChange={(e) => {
              if (e.value) setViewMode(e.value);
            }}
          />
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

      {/* Tag mentions — grouped by entity type */}
      {page.tag_mentions && page.tag_mentions.length > 0 && (() => {
        // Separate compounds (which may carry bioactivities) from other entity types
        type TagMentionItem = NonNullable<typeof page.tag_mentions>[number];
        type Bioactivity = { assay_type: string; value: string; unit: string; raw_text: string };
        const compounds: TagMentionItem[] = [];
        const grouped = new Map<string, TagMentionItem[]>();

        for (const tm of page.tag_mentions!) {
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
          <div className="mt-6">
            <h3 className="mb-3 text-sm font-medium text-text-secondary">
              Tag Mentions
            </h3>
            <div className="space-y-3">
              {/* Compounds — shown as cards with bioactivity tables */}
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
                            <Tag
                              value={tm.tag}
                              severity="success"
                              rounded
                            />
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

              {/* Other entity types — simple tag pills */}
              {[...grouped.entries()].map(([entityType, tags]) => {
                const config = ENTITY_TYPE_COLORS[entityType];
                return (
                  <div key={entityType} className="flex items-start gap-3">
                    <span className="mt-0.5 min-w-[120px] shrink-0 text-xs font-medium text-text-muted">
                      {entityType.replace(/_/g, " ")}
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {tags.map((tm, i) => (
                        <Tag
                          key={`${tm.tag}-${i}`}
                          value={tm.tag}
                          severity={config?.severity ?? "secondary"}
                          rounded
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}

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
                  <CopySmiles smiles={cm.smiles} />
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
                  <PubChemBadge
                    enrichment={enrichmentBySmiles?.get(
                      cm.canonical_smiles ?? "",
                    )}
                  />
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
                {RERUNNABLE_PAGE_WORKFLOWS.has(w.name) &&
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
                      className="!p-1"
                    />
                  )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
