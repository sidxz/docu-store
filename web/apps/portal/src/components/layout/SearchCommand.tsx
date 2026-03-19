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
} from "lucide-react";
import { ProgressSpinner } from "primereact/progressspinner";
import { Tag } from "primereact/tag";
import { useHierarchicalSearch } from "@/hooks/use-search";
import { useSearchStore } from "@/lib/stores/search-store";

interface SummaryHit {
  entity_type: "page" | "artifact";
  entity_id: string;
  artifact_id: string;
  score: number;
  summary_text?: string | null;
  artifact_title?: string | null;
  page_index?: number | null;
}

interface ChunkHit {
  page_id: string;
  artifact_id: string;
  page_index: number;
  score: number;
  text_preview?: string | null;
}

export function SearchCommand() {
  const { workspace } = useParams<{ workspace: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const search = useHierarchicalSearch();

  // Close panel on route change (layout persists across navigations)
  const prevPathname = useRef(pathname);
  useEffect(() => {
    if (pathname !== prevPathname.current) {
      prevPathname.current = pathname;
      setOpen(false);
      setQuery("");
      search.reset();
    }
  }, [pathname, search]);

  // Cmd+K global shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === "Escape" && open) {
        setOpen(false);
        setQuery("");
        search.reset();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, search]);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Click outside to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
        search.reset();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, search]);

  const handleSearch = () => {
    const trimmed = query.trim();
    if (!trimmed) return;
    search.mutate({ query_text: trimmed, include_chunks: true, limit: 6 });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
    if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
      search.reset();
    }
  };

  const handleViewAll = () => {
    useSearchStore.getState().setPendingQuery(query);
    router.push(`/${workspace}/search`);
  };

  const handleResultClick = () => {
    // Just close — route change effect will reset
    setOpen(false);
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
          className="flex items-center gap-2 rounded-full border border-border-default bg-surface-sunken px-4 py-1.5 text-sm text-text-muted transition-all hover:border-accent/40 hover:text-text-secondary hover:shadow-ds-sm"
        >
          <Search className="size-3.5" />
          <span>Search...</span>
          <kbd className="ml-1 rounded border border-border-default bg-surface px-1.5 py-0.5 text-xs font-medium text-text-muted">
            {"\u2318"}K
          </kbd>
        </button>
      ) : (
        <div className="flex items-center gap-2 rounded-full border border-accent bg-surface px-4 py-1.5 shadow-ds-sm animate-[expand_150ms_ease-out]"
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
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search documents..."
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
          />
          <button
            onClick={() => { setOpen(false); setQuery(""); search.reset(); }}
            className="shrink-0 text-text-muted transition-colors hover:text-text-primary"
            aria-label="Close search"
          >
            <kbd className="rounded border border-border-default bg-surface-sunken px-1.5 py-0.5 text-xs font-medium">
              ESC
            </kbd>
          </button>
        </div>
      )}

      {/* Results dropdown */}
      {open && (hasResults || search.isPending || search.isError) && (
        <div className="absolute left-1/2 top-full z-50 mt-2 w-[32rem] -translate-x-1/2 rounded-xl border border-border-default bg-surface-elevated shadow-ds-md animate-[fadeSlideDown_150ms_ease-out]">
          {/* Loading */}
          {search.isPending && (
            <div className="flex items-center justify-center py-8">
              <ProgressSpinner
                style={{ width: "1.5rem", height: "1.5rem" }}
                strokeWidth="3"
              />
            </div>
          )}

          {/* Error */}
          {search.isError && (
            <div className="px-4 py-6 text-center text-sm text-ds-error">
              Search failed. Is the backend running?
            </div>
          )}

          {/* Results */}
          {hasResults && !search.isPending && (
            <div className="max-h-[28rem] overflow-y-auto">
              {/* Summary hits */}
              {(search.data!.summary_hits?.length ?? 0) > 0 && (
                <div>
                  <div className="sticky top-0 z-10 bg-surface-elevated px-4 py-2 border-b border-border-subtle">
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
                      className="flex items-start gap-3 px-4 py-3 transition-colors hover:bg-surface-sunken"
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

              {/* Chunk hits */}
              {(search.data!.chunk_hits?.length ?? 0) > 0 && (
                <div>
                  <div className="sticky top-0 z-10 bg-surface-elevated px-4 py-2 border-b border-border-subtle border-t">
                    <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                      Text Matches
                    </span>
                  </div>
                  {(search.data!.chunk_hits as ChunkHit[]).map((c) => (
                    <Link
                      key={`c-${c.page_id}-${c.score}`}
                      href={`/${workspace}/documents/${c.artifact_id}/pages/${c.page_id}`}
                      onClick={handleResultClick}
                      className="flex items-start gap-3 px-4 py-3 transition-colors hover:bg-surface-sunken"
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

              {/* Footer — View all results */}
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

          {/* No results */}
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
        </div>
      )}
    </div>
  );
}
