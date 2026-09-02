"use client";

import { BookOpen, FileText, ExternalLink } from "lucide-react";
import type { SourceCitation } from "@docu-store/types";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";

interface CitationListProps {
  sources: SourceCitation[];
  workspace: string;
}

export function CitationList({ sources, workspace }: CitationListProps) {
  const devMode = useDevModeStore((s) => s.enabled);
  if (!sources.length) return null;

  return (
    <div className="mt-3">
      <p className="text-xs font-medium text-text-muted mb-2">
        Sources ({sources.length})
      </p>
      <div className="flex flex-wrap gap-2">
        {sources.map((source) => (
          <SourceCard key={source.citation_index} source={source} workspace={workspace} devMode={devMode} />
        ))}
      </div>
    </div>
  );
}

function SourceCard({
  source,
  workspace,
  devMode,
}: {
  source: SourceCitation;
  workspace: string;
  devMode: boolean;
}) {
  const title = source.artifact_title || "Unknown Document";
  const page = source.page_index != null ? `Page ${source.page_index + 1}` : null;

  // A literature citation names a paper this workspace does not hold: its
  // artifact_id is derived from the DOI and nothing is stored under it, so the
  // link has to leave the app. Marked as well as routed differently — a claim
  // taken from an abstract should not read as one taken off a page.
  const isLiterature = source.source_type === "literature";
  const href = isLiterature
    ? (source.external_url ?? "#")
    : source.page_id
      ? `/${workspace}/documents/${source.artifact_id}/pages/${source.page_id}`
      : `/${workspace}/documents/${source.artifact_id}`;

  return (
    <div className="inline-flex flex-col">
      <a
        href={href}
        {...(isLiterature ? { target: "_blank", rel: "noopener noreferrer" } : {})}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition-colors text-xs group ${
          isLiterature
            ? "border-dashed border-border-default bg-transparent hover:bg-surface-hover"
            : "border-border-default bg-surface-elevated hover:bg-surface-hover"
        }`}
      >
        <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-accent-light text-accent-text font-semibold text-[0.6875rem]">
          {source.citation_index}
        </span>
        {isLiterature ? (
          <BookOpen className="w-3 h-3 text-text-muted" />
        ) : (
          <FileText className="w-3 h-3 text-text-muted" />
        )}
        <span className="text-text-primary truncate max-w-[140px]">
          {title}
        </span>
        {isLiterature ? (
          <span className="text-text-muted italic">{"\u00B7"} abstract</span>
        ) : (
          page && <span className="text-text-muted">{"\u00B7"} {page}</span>
        )}
        <ExternalLink className="w-3 h-3 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
      </a>
      {/* Dev-mode: score + excerpt length */}
      {devMode && (
        <div className="flex gap-2 px-1 mt-0.5 text-[0.6875rem] font-mono text-text-muted">
          {source.similarity_score != null && (
            <span>score: <span className="text-blue-500">{source.similarity_score.toFixed(3)}</span></span>
          )}
          {source.text_excerpt && (
            <span>excerpt: <span className="text-purple-500">{source.text_excerpt.length}ch</span></span>
          )}
        </div>
      )}
    </div>
  );
}
