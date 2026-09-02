"use client";

import { Library, X } from "lucide-react";
import type { LiteratureHit } from "@docu-store/types";

import { useChatStore } from "@/lib/stores/chat-store";
import { LiteratureResultCard } from "./LiteratureResultCard";

/**
 * The papers the last search returned. This panel, not the prose, is the point
 * of the surface: the agent has only read abstracts, so its answer orients you
 * while the cards are what you act on.
 */
export function LiteraturePanel({
  results,
  onClose,
}: {
  results: LiteratureHit[];
  onClose: () => void;
}) {
  const ingestable = results.filter((r) => r.is_ingestable).length;

  // Which of these the answer actually leaned on. Matched by external_url
  // rather than by citation id: the id is a uuid5 of the same URL, so the URL
  // is the thing they genuinely share and needs no hashing in the browser.
  const finalSources = useChatStore((s) => s.finalSources);
  const streamingSources = useChatStore((s) => s.streamingSources);
  const citedUrls = new Set(
    (finalSources ?? streamingSources)
      .map((s) => s.external_url)
      .filter((u): u is string => !!u),
  );
  const citedCount = results.filter((r) => citedUrls.has(r.url)).length;

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
          />
        ))}
      </div>
    </div>
  );
}
