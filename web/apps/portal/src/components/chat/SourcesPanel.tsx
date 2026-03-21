"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { FileText, X, ChevronDown, ChevronRight, Users, Calendar } from "lucide-react";
import { Skeleton } from "primereact/skeleton";
import { Button } from "primereact/button";
import type { SourceCitation } from "@docu-store/types";
import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { useChatStore } from "@/lib/stores/chat-store";
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
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-default">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-text-muted" />
          <span className="text-sm font-medium text-text-primary">
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
  const highlightedCitation = useChatStore((s) => s.highlightedCitation);

  // Auto-expand pages when a citation in this card is highlighted
  useEffect(() => {
    if (highlightedCitation != null && citations.some((c) => c.citation_index === highlightedCitation)) {
      setPagesExpanded(true);
    }
  }, [highlightedCitation, citations]);

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
    <div className="rounded-lg border border-border-default bg-surface-elevated overflow-hidden">
      {/* Thumbnail + title + metadata */}
      <div className="flex gap-3 p-3">
        <SourceThumbnail src={thumbSrc} href={artifactHref} />
        <div className="min-w-0 flex-1">
          <Link
            href={artifactHref}
            className="text-sm font-medium text-accent-text hover:underline line-clamp-2"
          >
            {title}
          </Link>

          {/* Authors */}
          {authors.length > 0 && (
            <div className="flex items-center gap-1 mt-1">
              <Users className="w-3 h-3 text-text-muted flex-shrink-0" />
              <p className="text-xs text-text-muted truncate">
                {authors.join(", ")}
              </p>
            </div>
          )}

          {/* Date */}
          {formattedDate && (
            <div className="flex items-center gap-1 mt-0.5">
              <Calendar className="w-3 h-3 text-text-muted flex-shrink-0" />
              <p className="text-xs text-text-muted">
                {formattedDate}
              </p>
            </div>
          )}

          {/* Score */}
          {best.similarity_score != null && (
            <span className="inline-block mt-1.5 text-[11px] font-mono text-text-muted">
              relevance: {best.similarity_score.toFixed(2)}
            </span>
          )}
        </div>
      </div>

      {/* Pages toggle + collapsible rows */}
      {citations.length > 0 && (
        <div className="border-t border-border-subtle">
          <button
            onClick={() => setPagesExpanded(!pagesExpanded)}
            className="flex items-center gap-1.5 w-full px-3 py-1.5 text-xs text-text-muted hover:bg-surface-hover transition-colors"
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
  const highlightedCitation = useChatStore((s) => s.highlightedCitation);
  const rowRef = useRef<HTMLAnchorElement>(null);
  const isHighlighted = highlightedCitation === citation.citation_index;

  // Scroll into view and trigger flash animation when highlighted
  useEffect(() => {
    if (isHighlighted && rowRef.current) {
      rowRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
      // Re-trigger animation by removing and re-adding the class
      rowRef.current.classList.remove("citation-highlight");
      // Force reflow
      void rowRef.current.offsetWidth;
      rowRef.current.classList.add("citation-highlight");
    }
  }, [isHighlighted]);

  const pageHref = citation.page_id
    ? `/${workspace}/documents/${citation.artifact_id}/pages/${citation.page_id}`
    : `/${workspace}/documents/${citation.artifact_id}`;

  return (
    <Link
      ref={rowRef}
      href={pageHref}
      className="flex items-start gap-2 px-3 py-2 hover:bg-surface-hover transition-colors border-t border-border-subtle rounded-sm"
    >
      <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-accent-light text-accent-text font-semibold text-[10px] flex-shrink-0 mt-0.5">
        {citation.citation_index}
      </span>

      <div className="min-w-0 flex-1">
        <span className="text-xs font-medium text-text-primary">
          {citation.page_name || (citation.page_index != null ? `Page ${citation.page_index + 1}` : "Document")}
        </span>
        {citation.text_excerpt && (
          <p className="text-[11px] text-text-muted mt-0.5 line-clamp-2 leading-relaxed">
            {citation.text_excerpt}
          </p>
        )}
        {devMode && (
          <div className="flex gap-2 mt-0.5 text-[10px] font-mono text-text-muted">
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
      <Link href={href} className="flex items-center justify-center w-16 h-20 rounded bg-surface-elevated flex-shrink-0">
        <FileText className="w-6 h-6 text-text-muted" />
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
          className="w-16 h-20 rounded-md border border-border-default object-cover object-top"
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
