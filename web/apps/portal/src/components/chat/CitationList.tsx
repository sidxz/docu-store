"use client";

import { FileText, ExternalLink } from "lucide-react";
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
      <p className="text-xs font-medium text-surface-500 dark:text-surface-400 mb-2">
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
  const href = source.page_id
    ? `/${workspace}/documents/${source.artifact_id}/pages/${source.page_id}`
    : `/${workspace}/documents/${source.artifact_id}`;

  return (
    <div className="inline-flex flex-col">
      <a
        href={href}
        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-0 dark:bg-surface-800 hover:bg-surface-50 dark:hover:bg-surface-750 transition-colors text-xs group"
      >
        <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-semibold text-[10px]">
          {source.citation_index}
        </span>
        <FileText className="w-3 h-3 text-surface-400" />
        <span className="text-surface-700 dark:text-surface-300 truncate max-w-[140px]">
          {title}
        </span>
        {page && (
          <span className="text-surface-400 dark:text-surface-500">{"\u00B7"} {page}</span>
        )}
        <ExternalLink className="w-3 h-3 text-surface-400 opacity-0 group-hover:opacity-100 transition-opacity" />
      </a>
      {/* Dev-mode: score + excerpt length */}
      {devMode && (
        <div className="flex gap-2 px-1 mt-0.5 text-[10px] font-mono text-surface-400">
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
