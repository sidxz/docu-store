"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { FileText, X, ChevronDown, ChevronRight, Users, Calendar, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import type { SourceCitation } from "@docu-store/types";
import { AuthThumbnail } from "@/components/ui/TableThumbnail";
import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { usePointerDrag } from "@/hooks/use-pointer-drag";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { useChatStore } from "@/lib/stores/chat-store";
import { useAnalytics } from "@/hooks/use-analytics";
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
          variant="ghost"
          size="icon-sm"
          className="rounded-full"
          onClick={onClose}
          aria-label="Close sources"
        >
          <X className="w-3.5 h-3.5" />
        </Button>
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
        <AuthThumbnail
          src={thumbSrc}
          href={artifactHref}
          size="xs"
          errorFallback={
            <Link href={artifactHref} className="flex items-center justify-center w-16 h-20 rounded bg-surface-elevated flex-shrink-0">
              <FileText className="w-6 h-6 text-text-muted" />
            </Link>
          }
        />
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
  const [previewOpen, setPreviewOpen] = useState(false);
  const highlightedCitation = useChatStore((s) => s.highlightedCitation);
  const { trackEvent } = useAnalytics();
  const rowRef = useRef<HTMLDivElement>(null);
  const flashCount = useRef(0);
  const isHighlighted = highlightedCitation === citation.citation_index;

  // Increment counter to re-trigger animation via key change
  if (isHighlighted) flashCount.current += 1;

  // Scroll into view when highlighted
  useEffect(() => {
    if (isHighlighted && rowRef.current) {
      rowRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [isHighlighted]);

  const pageHref = citation.page_id
    ? `/${workspace}/documents/${citation.artifact_id}/pages/${citation.page_id}`
    : `/${workspace}/documents/${citation.artifact_id}`;

  const previewSrc = citation.page_index != null
    ? `${API_URL}/artifacts/${citation.artifact_id}/pages/${citation.page_index}/image`
    : null;

  const pageLabel = citation.page_name || (citation.page_index != null ? `Page ${citation.page_index + 1}` : "Document");

  return (
    <>
      <div
        key={flashCount.current}
        ref={rowRef}
        onClick={() => {
          if (previewSrc) {
            if (!previewOpen) {
              trackEvent("source_preview_opened", {
                artifact_id: citation.artifact_id,
                citation_index: citation.citation_index,
              });
            }
            setPreviewOpen(!previewOpen);
          }
        }}
        className={`group flex items-start gap-2 px-3 py-2 hover:bg-surface-hover transition-colors border-t border-border-subtle rounded-sm ${previewSrc ? "cursor-pointer" : ""} ${isHighlighted ? "citation-highlight" : ""}`}
      >
        <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-accent-light text-accent-text font-semibold text-[10px] flex-shrink-0 mt-0.5">
          {citation.citation_index}
        </span>

        <div className="min-w-0 flex-1">
          <Link
            href={pageHref}
            onClick={(e) => {
              e.stopPropagation();
              trackEvent("citation_clicked", {
                citation_index: citation.citation_index,
                artifact_id: citation.artifact_id,
                source: "panel",
              });
            }}
            className="text-xs font-medium text-accent-text hover:underline"
          >
            {pageLabel}
          </Link>
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

        {previewSrc && (
          <Eye className={`w-3.5 h-3.5 flex-shrink-0 mt-0.5 transition-colors ${previewOpen ? "text-accent-text" : "text-text-muted opacity-0 group-hover:opacity-100"}`} />
        )}
      </div>

      <PagePreviewDialog
        visible={previewOpen}
        src={previewSrc}
        title={pageLabel}
        pageHref={pageHref}
        onHide={() => setPreviewOpen(false)}
      />
    </>
  );
}

function PagePreviewDialog({
  visible,
  src,
  title,
  pageHref,
  onHide,
}: {
  visible: boolean;
  src: string | null;
  title: string;
  pageHref: string;
  onHide: () => void;
}) {
  const { blobUrl, error } = useAuthBlobUrl(visible && src ? src : "");
  const drag = usePointerDrag();

  return (
    <Dialog
      modal={false}
      open={visible}
      onOpenChange={(open) => {
        if (!open) {
          onHide();
          drag.reset();
        }
      }}
    >
      <DialogContent
        showOverlay={false}
        style={drag.style}
        className="gap-3 border border-white/10 bg-surface-primary/80 p-3 shadow-2xl backdrop-blur-xl sm:max-w-[min(56rem,70vw)]"
      >
        <DialogHeader
          onPointerDown={drag.onPointerDown}
          className="flex-row items-center gap-2 space-y-0 cursor-move select-none"
        >
          <Eye className="w-4 h-4 text-text-muted flex-shrink-0" />
          <DialogTitle className="truncate text-sm font-medium leading-none">{title}</DialogTitle>
        </DialogHeader>

        <div className="resize overflow-auto rounded-md bg-black/30 border border-border-subtle">
          {!src && (
            <div className="flex items-center justify-center h-40 text-text-muted text-sm">
              No preview available
            </div>
          )}
          {src && !blobUrl && !error && (
            <div className="flex items-center justify-center" style={{ minHeight: "20rem" }}>
              <Skeleton className="h-[20rem] w-full rounded-none" />
            </div>
          )}
          {error && (
            <div className="flex flex-col items-center justify-center h-40 gap-2 text-text-muted">
              <FileText className="w-6 h-6" />
              <span className="text-sm">Preview unavailable</span>
            </div>
          )}
          {blobUrl && (
            <img
              src={blobUrl}
              alt={title}
              className="max-h-[70vh] w-full object-contain"
            />
          )}
        </div>

        <div className="flex justify-end">
          <Button asChild variant="ghost" size="sm" className="text-xs">
            <Link href={pageHref}>Open full page</Link>
          </Button>
        </div>
      </DialogContent>
    </Dialog>
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
