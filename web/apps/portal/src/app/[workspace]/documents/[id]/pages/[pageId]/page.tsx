"use client";

import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, BookOpen, Loader2 } from "lucide-react";

import { MoleculeStructure } from "@docu-store/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { WorkflowStatusBadge } from "@/components/WorkflowStatusBadge";
import { usePage, usePageWorkflows } from "@/hooks/use-pages";

const ENTITY_TYPE_COLORS: Record<string, string> = {
  compound_name: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
  target: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
  disease: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400",
};

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
      />

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
