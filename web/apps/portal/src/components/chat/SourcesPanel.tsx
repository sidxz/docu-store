"use client";

import { useState } from "react";
import Link from "next/link";
import { FileText, X, ChevronDown, ChevronRight, Users, Calendar } from "lucide-react";
import { Skeleton } from "primereact/skeleton";
import { Button } from "primereact/button";
import type { SourceCitation } from "@docu-store/types";
import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { API_URL } from "@/lib/constants";

interface SourcesPanelProps {
  sources: SourceCitation[];
  workspace: string;
  onClose: () => void;
}

export function SourcesPanel({ sources, workspace, onClose }: SourcesPanelProps) {
  const devMode = useDevModeStore((s) => s.enabled);

  if (!sources.length) return null;

  // Group by artifact_id, preserving order of first appearance
  const artifactMap = new Map<string, SourceCitation[]>();
  for (const s of sources) {
    const key = s.artifact_id;
    if (!artifactMap.has(key)) artifactMap.set(key, []);
    artifactMap.get(key)!.push(s);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-surface-200 dark:border-surface-700">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-surface-500" />
          <span className="text-sm font-medium text-surface-700 dark:text-surface-300">
            Sources ({sources.length})
          </span>
        </div>
        <Button
          icon={<X className="w-3.5 h-3.5" />}
          onClick={onClose}
          className="p-button-text p-button-sm p-button-rounded"
          aria-label="Close sources"
        />
      </div>

      {/* Source cards */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {Array.from(artifactMap.entries()).map(([artifactId, citations]) => (
          <SourceArtifactCard
            key={artifactId}
            citations={citations}
            workspace={workspace}
            devMode={devMode}
          />
        ))}
      </div>
    </div>
  );
}

function SourceArtifactCard({
  citations,
  workspace,
  devMode,
}: {
  citations: SourceCitation[];
  workspace: string;
  devMode: boolean;
}) {
  const [pagesExpanded, setPagesExpanded] = useState(false);

  const best = citations.reduce((a, b) =>
    (b.similarity_score ?? 0) > (a.similarity_score ?? 0) ? b : a,
  );
  const title = best.artifact_title || "Unknown Document";
  const artifactHref = `/${workspace}/documents/${best.artifact_id}`;
  const authors = best.authors ?? [];
  const date = best.presentation_date;

  // Use the first page's index for thumbnail
  const thumbPage = citations.find((c) => c.page_index != null);
  const thumbIdx = thumbPage?.page_index ?? 0;
  const thumbSrc = `${API_URL}/artifacts/${best.artifact_id}/pages/${thumbIdx}/image?size=thumb`;

  const formattedDate = date ? formatDate(date) : null;

  return (
    <div className="rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-0 dark:bg-surface-800 overflow-hidden">
      {/* Thumbnail + title + metadata */}
      <div className="flex gap-3 p-3">
        <SourceThumbnail src={thumbSrc} href={artifactHref} />
        <div className="min-w-0 flex-1">
          <Link
            href={artifactHref}
            className="text-sm font-medium text-primary-600 dark:text-primary-400 hover:underline line-clamp-2"
          >
            {title}
          </Link>

          {/* Authors */}
          {authors.length > 0 && (
            <div className="flex items-center gap-1 mt-1">
              <Users className="w-3 h-3 text-surface-400 flex-shrink-0" />
              <p className="text-xs text-surface-500 dark:text-surface-400 truncate">
                {authors.join(", ")}
              </p>
            </div>
          )}

          {/* Date */}
          {formattedDate && (
            <div className="flex items-center gap-1 mt-0.5">
              <Calendar className="w-3 h-3 text-surface-400 flex-shrink-0" />
              <p className="text-xs text-surface-500 dark:text-surface-400">
                {formattedDate}
              </p>
            </div>
          )}

          {/* Score */}
          {best.similarity_score != null && (
            <span className="inline-block mt-1.5 text-[11px] font-mono text-surface-400 dark:text-surface-500">
              relevance: {best.similarity_score.toFixed(2)}
            </span>
          )}
        </div>
      </div>

      {/* Pages toggle + collapsible rows */}
      {citations.length > 0 && (
        <div className="border-t border-surface-100 dark:border-surface-700">
          <button
            onClick={() => setPagesExpanded(!pagesExpanded)}
            className="flex items-center gap-1.5 w-full px-3 py-1.5 text-xs text-surface-500 dark:text-surface-400 hover:bg-surface-50 dark:hover:bg-surface-750 transition-colors"
          >
            {pagesExpanded ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
            <span>
              {citations.length} {citations.length === 1 ? "citation" : "citations"}
            </span>
          </button>

          {pagesExpanded && (
            <div>
              {citations.map((c) => (
                <SourcePageRow key={c.citation_index} citation={c} workspace={workspace} devMode={devMode} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SourcePageRow({
  citation,
  workspace,
  devMode,
}: {
  citation: SourceCitation;
  workspace: string;
  devMode: boolean;
}) {
  const pageHref = citation.page_id
    ? `/${workspace}/documents/${citation.artifact_id}/pages/${citation.page_id}`
    : `/${workspace}/documents/${citation.artifact_id}`;

  return (
    <Link
      href={pageHref}
      className="flex items-start gap-2 px-3 py-2 hover:bg-surface-50 dark:hover:bg-surface-750 transition-colors border-t border-surface-100 dark:border-surface-700"
    >
      <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-semibold text-[10px] flex-shrink-0 mt-0.5">
        {citation.citation_index}
      </span>

      <div className="min-w-0 flex-1">
        <span className="text-xs font-medium text-surface-700 dark:text-surface-300">
          {citation.page_name || (citation.page_index != null ? `Page ${citation.page_index + 1}` : "Document")}
        </span>
        {citation.text_excerpt && (
          <p className="text-[11px] text-surface-500 dark:text-surface-400 mt-0.5 line-clamp-2 leading-relaxed">
            {citation.text_excerpt}
          </p>
        )}
        {devMode && (
          <div className="flex gap-2 mt-0.5 text-[10px] font-mono text-surface-400">
            {citation.similarity_score != null && (
              <span>score: <span className="text-blue-500">{citation.similarity_score.toFixed(3)}</span></span>
            )}
            {citation.text_excerpt && (
              <span>excerpt: <span className="text-purple-500">{citation.text_excerpt.length}ch</span></span>
            )}
          </div>
        )}
      </div>
    </Link>
  );
}

function SourceThumbnail({ src, href }: { src: string; href: string }) {
  const { blobUrl, error } = useAuthBlobUrl(src);

  if (error) {
    return (
      <Link href={href} className="flex items-center justify-center w-16 h-20 rounded bg-surface-100 dark:bg-surface-700 flex-shrink-0">
        <FileText className="w-6 h-6 text-surface-400" />
      </Link>
    );
  }

  return (
    <Link href={href} className="relative w-16 h-20 flex-shrink-0">
      {!blobUrl ? (
        <Skeleton width="4rem" height="5rem" borderRadius="0.375rem" />
      ) : (
        <img
          src={blobUrl}
          alt=""
          className="w-16 h-20 rounded-md border border-surface-200 dark:border-surface-700 object-cover object-top"
        />
      )}
    </Link>
  );
}

function formatDate(dateStr: string): string | null {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return dateStr;
  }
}
