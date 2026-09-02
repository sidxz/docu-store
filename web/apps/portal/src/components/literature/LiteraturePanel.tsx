"use client";

import { Library, X } from "lucide-react";
import type { LiteratureHit, SourceCitation } from "@docu-store/types";

import { useChatStore } from "@/lib/stores/chat-store";
import { LiteratureResultCard } from "./LiteratureResultCard";

/**
 * The papers the last search returned. This panel, not the prose, is the point
 * of the surface: the agent has only read abstracts, so its answer orients you
 * while the cards are what you act on.
 */
export function LiteraturePanel({
  results,
  sources,
  onClose,
}: {
  results: LiteratureHit[];
  /** Citations from the same turn as `results` — passed in rather than read
   *  from the store so a reopened conversation shows its own, not the last
   *  streamed one's. */
  sources: SourceCitation[];
  onClose: () => void;
}) {
  const ingestable = results.filter((r) => r.is_ingestable).length;

  // Which of these the answer actually leaned on. Matched by external_url
  // rather than by citation id: the id is a uuid5 of the same URL, so the URL
  // is the thing they genuinely share and needs no hashing in the browser.
  const citedUrls = new Set(
    sources.map((s) => s.external_url).filter((u): u is string => !!u),
  );
  const citedCount = results.filter((r) => citedUrls.has(r.url)).length;

  // The [n] in the answer has to lead somewhere. Deep Research scrolls its
  // sources panel to the cited row; this is the same idea against papers,
  // resolved through the URL the citation and the hit share.
  const highlightedCitation = useChatStore((s) => s.highlightedCitation);
  const indexByUrl = new Map<string, number>();
  for (const s of sources) {
    if (s.external_url && !indexByUrl.has(s.external_url)) {
      indexByUrl.set(s.external_url, s.citation_index);
    }
  }
  const highlightedUrl = sources.find(
    (s) => s.citation_index === highlightedCitation,
  )?.external_url;

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-border-default px-4 py-3">
        <div className="flex items-center gap-2">
          <Library className="h-4 w-4 text-rose-500" />
          <h2 className="text-sm font-medium text-text-primary">Papers</h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close papers panel"
          className="text-text-muted hover:text-text-primary"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <p className="px-4 py-2 text-xs text-text-muted">
        {results.length} found · {ingestable} can be added ·{" "}
        {results.length - ingestable} readable at the publisher only
        {citedCount > 0 && (
          <>
            {" · "}
            <span className="text-emerald-600 dark:text-emerald-400">
              {citedCount} cited
            </span>
          </>
        )}
      </p>

      <div className="flex-1 space-y-2 overflow-y-auto px-4 pb-4">
        {results.map((hit) => (
          <LiteratureResultCard
            key={`${hit.source}-${hit.external_id}`}
            hit={hit}
            cited={citedUrls.has(hit.url)}
            citationIndex={indexByUrl.get(hit.url)}
            highlighted={!!highlightedUrl && hit.url === highlightedUrl}
          />
        ))}
      </div>
    </div>
  );
}
