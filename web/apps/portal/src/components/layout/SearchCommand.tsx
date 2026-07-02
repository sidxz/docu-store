"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import {
  Search,
  Loader2,
  AlignLeft,
  ArrowRight,
  FileText,
  BookOpen,
  X,
  Trash2,
} from "lucide-react";
import { Tag } from "primereact/tag";
import { OverlayPanel } from "primereact/overlaypanel";
import type { SummaryHit, ChunkHit } from "@docu-store/types";
import { useHierarchicalSearchMutation } from "@/hooks/use-search";
import { useRecentSearches, useDeleteSearchEntry, useClearSearchHistory } from "@/hooks/use-activity";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";

export function SearchCommand() {
  const { workspace } = useParams<{ workspace: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const recentOverlayRef = useRef<OverlayPanel>(null);
  const resultsOverlayRef = useRef<OverlayPanel>(null);
  const inputBarRef = useRef<HTMLDivElement>(null);
  const search = useHierarchicalSearchMutation();
  const { data: recentSearches } = useRecentSearches(5);
  const deleteEntry = useDeleteSearchEntry();
  const clearHistory = useClearSearchHistory();

  const closeAll = () => {
    setOpen(false);
    setQuery("");
    search.reset();
    recentOverlayRef.current?.hide();
    resultsOverlayRef.current?.hide();
  };

  // Close panel on route change
  const prevPathname = useRef(pathname);
  useEffect(() => {
    if (pathname !== prevPathname.current) {
      prevPathname.current = pathname;
      closeAll();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  // Cmd+K global shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === "Escape" && open) {
        closeAll();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Focus input when opened; show recent searches overlay after a brief delay
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.focus());
      // Show recent searches after topbar reflow settles
      const t = setTimeout(() => {
        if (inputBarRef.current && recentSearches?.length && !query) {
          recentOverlayRef.current?.show(null, inputBarRef.current);
        }
      }, 220);
      return () => clearTimeout(t);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Click outside to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        // Check if click is inside an overlay panel
        const overlays = document.querySelectorAll(".p-overlaypanel");
        for (const overlay of overlays) {
          if (overlay.contains(e.target as Node)) return;
        }
        closeAll();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Show/hide results overlay based on search state
  useEffect(() => {
    const hasData = search.data || search.isPending || search.isError;
    if (open && hasData && inputBarRef.current) {
      recentOverlayRef.current?.hide();
      resultsOverlayRef.current?.show(null, inputBarRef.current);
    } else if (!hasData) {
      resultsOverlayRef.current?.hide();
    }
  }, [open, search.data, search.isPending, search.isError]);

  const handleSearch = () => {
    const trimmed = query.trim();
    if (!trimmed) return;
    recentOverlayRef.current?.hide();
    search.mutate({ query_text: trimmed, include_chunks: true, limit: 6 });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
    if (e.key === "Escape") closeAll();
  };

  const handleViewAll = () => {
    closeAll();
    router.push(`/${workspace}/search?q=${encodeURIComponent(query)}&mode=hierarchical`);
  };

  const handleResultClick = () => {
    closeAll();
  };

  const hasResults =
    search.data &&
    ((search.data.summary_hits?.length ?? 0) > 0 ||
      (search.data.chunk_hits?.length ?? 0) > 0);

  return (
    <div ref={panelRef} className="relative">
      {/* Pill / Expanded input */}
      {!open ? (
        <button
          onClick={() => setOpen(true)}
          className="flex items-center gap-2 rounded-full border border-border-default bg-surface-sunken px-4 py-1.5 text-sm text-text-muted transition-all hover:border-primary/40 hover:text-text-secondary hover:shadow-ds-sm"
        >
          <Search className="size-3.5" />
          <span>Search...</span>
          <kbd className="ml-1 rounded border border-border-default bg-surface px-1.5 py-0.5 text-xs font-medium text-text-muted">
            {"\u2318"}K
          </kbd>
        </button>
      ) : (
        <div
          ref={inputBarRef}
          className="flex items-center gap-2 rounded-full border border-primary bg-surface px-4 py-1.5 shadow-ds-sm"
          style={{ minWidth: "24rem" }}
        >
          <button
            onClick={handleSearch}
            disabled={!query.trim() || search.isPending}
            className="shrink-0 text-accent-text transition-colors hover:text-accent-hover disabled:text-text-muted"
            aria-label="Search"
          >
            {search.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Search className="size-4" />
            )}
          </button>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              if (!e.target.value.trim()) {
                resultsOverlayRef.current?.hide();
                if (recentSearches?.length && inputBarRef.current) {
                  recentOverlayRef.current?.show(null, inputBarRef.current);
                }
              } else {
                recentOverlayRef.current?.hide();
              }
            }}
            onKeyDown={handleKeyDown}
            placeholder="Search documents..."
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
          />
          <button
            onClick={closeAll}
            className="shrink-0 text-text-muted transition-colors hover:text-text-primary"
            aria-label="Close search"
          >
            <kbd className="rounded border border-border-default bg-surface-sunken px-1.5 py-0.5 text-xs font-medium">
              ESC
            </kbd>
          </button>
        </div>
      )}

      {/* Recent searches overlay — PrimeReact OverlayPanel for smooth transitions */}
      <OverlayPanel
        ref={recentOverlayRef}
        dismissable={false}
        className="!p-0 !rounded-xl !border-border-default !bg-surface-elevated/60 !shadow-ds-md !backdrop-blur-2xl w-[32rem]"
      >
        <div className="flex items-center justify-between px-4 py-2 border-b border-border-subtle">
          <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
            Recent Searches
          </span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              clearHistory.mutate();
              recentOverlayRef.current?.hide();
            }}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-text-muted transition-colors hover:bg-ds-error/10 hover:text-ds-error"
          >
            <Trash2 className="h-3 w-3" />
            Clear all
          </button>
        </div>
        {recentSearches?.map((entry, i) => (
          <div
            key={`${entry.query_text}-${i}`}
            className="group flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-white/10"
          >
            <Search className="h-3.5 w-3.5 shrink-0 text-text-muted" />
            <button
              className="min-w-0 flex-1 truncate text-left text-sm text-text-primary"
              onClick={() => {
                setQuery(entry.query_text);
                recentOverlayRef.current?.hide();
                search.mutate({ query_text: entry.query_text, include_chunks: true, limit: 6 });
              }}
            >
              {entry.query_text}
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                deleteEntry.mutate(entry.query_text);
              }}
              className="shrink-0 rounded p-0.5 text-text-muted opacity-0 transition-all hover:bg-ds-error/10 hover:text-ds-error group-hover:opacity-100"
              aria-label={`Remove "${entry.query_text}" from history`}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </OverlayPanel>

      {/* Results overlay — PrimeReact OverlayPanel */}
      <OverlayPanel
        ref={resultsOverlayRef}
        dismissable={false}
        className="!p-0 !rounded-xl !border-border-default !bg-surface-elevated/60 !shadow-ds-md !backdrop-blur-2xl w-[32rem]"
      >
        {search.isPending && (
          <LoadingSpinner size="sm" className="flex items-center justify-center py-8" />
        )}

        {search.isError && (
          <div className="px-4 py-6 text-center text-sm text-ds-error">
            Search failed. Is the backend running?
          </div>
        )}

        {hasResults && !search.isPending && (
          <div className="max-h-[28rem] overflow-y-auto">
            {(search.data!.summary_hits?.length ?? 0) > 0 && (
              <div>
                <div className="sticky top-0 z-10 bg-surface-elevated/80 backdrop-blur-md px-4 py-2 border-b border-border-subtle">
                  <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Summary Matches
                  </span>
                </div>
                {(search.data!.summary_hits as SummaryHit[]).map((h) => (
                  <Link
                    key={`s-${h.entity_id}`}
                    href={
                      h.entity_type === "artifact"
                        ? `/${workspace}/documents/${h.artifact_id}`
                        : `/${workspace}/documents/${h.artifact_id}/pages/${h.entity_id}`
                    }
                    onClick={handleResultClick}
                    className="flex items-start gap-3 px-4 py-3 transition-colors hover:bg-white/10"
                  >
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-light">
                      {h.entity_type === "artifact" ? (
                        <FileText className="size-3.5 text-accent-text" />
                      ) : (
                        <BookOpen className="size-3.5 text-accent-text" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-text-primary">
                          {h.entity_type === "page" && h.artifact_title
                            ? `${h.artifact_title} | Page ${(h.page_index ?? 0) + 1}`
                            : h.artifact_title ?? h.entity_id.slice(0, 8)}
                        </span>
                        <span className="shrink-0 text-xs font-medium text-accent-text">
                          {Math.round(h.score * 100)}%
                        </span>
                      </div>
                      {h.summary_text && (
                        <p className="mt-0.5 truncate text-xs text-text-muted">
                          {h.summary_text.slice(0, 120)}
                        </p>
                      )}
                    </div>
                    <Tag
                      value={h.entity_type}
                      severity={h.entity_type === "artifact" ? "info" : "secondary"}
                      className="shrink-0"
                    />
                  </Link>
                ))}
              </div>
            )}

            {(search.data!.chunk_hits?.length ?? 0) > 0 && (
              <div>
                <div className="sticky top-0 z-10 bg-surface-elevated/80 backdrop-blur-md px-4 py-2 border-b border-border-subtle border-t">
                  <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Text Matches
                  </span>
                </div>
                {(search.data!.chunk_hits as ChunkHit[]).map((c) => (
                  <Link
                    key={`c-${c.page_id}-${c.score}`}
                    href={`/${workspace}/documents/${c.artifact_id}/pages/${c.page_id}`}
                    onClick={handleResultClick}
                    className="flex items-start gap-3 px-4 py-3 transition-colors hover:bg-white/10"
                  >
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-border-subtle">
                      <AlignLeft className="size-3.5 text-text-muted" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-text-primary">
                          Page {c.page_index + 1}
                        </span>
                        <span className="text-xs font-medium text-accent-text">
                          {Math.round(c.score * 100)}%
                        </span>
                      </div>
                      {c.text_preview && (
                        <p className="mt-0.5 line-clamp-2 text-xs text-text-muted">
                          {c.text_preview}
                        </p>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
            )}

            <div className="border-t border-border-default px-4 py-2.5">
              <button
                onClick={handleViewAll}
                className="flex w-full items-center justify-center gap-1.5 text-xs font-medium text-accent-text transition-colors hover:text-accent-hover"
              >
                View all results
                <ArrowRight className="size-3" />
              </button>
            </div>
          </div>
        )}

        {search.data &&
          !search.isPending &&
          (search.data.summary_hits?.length ?? 0) === 0 &&
          (search.data.chunk_hits?.length ?? 0) === 0 && (
            <div className="px-4 py-8 text-center">
              <Search className="size-8 text-text-muted" />
              <p className="mt-2 text-sm text-text-muted">
                No results found for &ldquo;{query}&rdquo;
              </p>
            </div>
          )}
      </OverlayPanel>
    </div>
  );
}
