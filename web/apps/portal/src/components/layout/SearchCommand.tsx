"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";
import {
  Search,
  AlignLeft,
  ArrowRight,
  FileText,
  BookOpen,
  X,
  Trash2,
} from "lucide-react";
import type { SummaryHit, ChunkHit } from "@docu-store/types";
import { useHierarchicalSearchMutation } from "@/hooks/use-search";
import { useRecentSearches, useDeleteSearchEntry, useClearSearchHistory } from "@/hooks/use-activity";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { EntityTypeBadge } from "@/components/ui/EntityTypeBadge";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";

// Debounce delay for live search-as-you-type, matching TagFilter's convention.
const SEARCH_DEBOUNCE_MS = 200;

export function SearchCommand() {
  const { workspace } = useParams<{ workspace: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const search = useHierarchicalSearchMutation();
  const { data: recentSearches } = useRecentSearches(5);
  const deleteEntry = useDeleteSearchEntry();
  const clearHistory = useClearSearchHistory();

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) {
      setQuery("");
      search.reset();
    }
  };

  // Close dialog on route change (e.g. browser back/forward)
  const prevPathname = useRef(pathname);
  useEffect(() => {
    if (pathname !== prevPathname.current) {
      prevPathname.current = pathname;
      handleOpenChange(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  // Cmd+K / Ctrl+K global shortcut to open. Esc-to-close and outside-click
  // are handled natively by the underlying Radix Dialog.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(true);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  // Debounced live search as the query changes — same hook/endpoint as before.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = query.trim();
    if (!trimmed) {
      search.reset();
      return;
    }

    debounceRef.current = setTimeout(() => {
      search.mutate({ query_text: trimmed, include_chunks: true, limit: 6 });
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const handleResultSelect = (href: string) => {
    handleOpenChange(false);
    router.push(href);
  };

  const handleViewAll = () => {
    const trimmed = query.trim();
    handleOpenChange(false);
    router.push(`/${workspace}/search?q=${encodeURIComponent(trimmed)}&mode=hierarchical`);
  };

  const hasResults =
    search.data &&
    ((search.data.summary_hits?.length ?? 0) > 0 ||
      (search.data.chunk_hits?.length ?? 0) > 0);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-full border border-border-default bg-surface-sunken px-4 py-1.5 text-sm text-text-muted transition-all hover:border-primary/40 hover:text-text-secondary hover:shadow-ds-sm"
      >
        <Search className="size-3.5" />
        <span>Search...</span>
        <kbd className="ml-1 rounded border border-border-default bg-surface px-1.5 py-0.5 text-xs font-medium text-text-muted">
          {"⌘"}K
        </kbd>
      </button>

      <CommandDialog
        open={open}
        onOpenChange={handleOpenChange}
        title="Search"
        description="Search documents, pages, and text"
        shouldFilter={false}
      >
        <CommandInput
          value={query}
          onValueChange={setQuery}
          placeholder="Search documents, pages, compounds…"
        />
        <CommandList>
          {!query.trim() && (recentSearches?.length ?? 0) > 0 && (
            <CommandGroup heading="Recent">
              {recentSearches!.map((entry, i) => (
                <CommandItem
                  key={`${entry.query_text}-${i}`}
                  value={`recent-${entry.query_text}-${i}`}
                  onSelect={() => setQuery(entry.query_text)}
                  className="group"
                >
                  <Search className="size-3.5 text-text-muted" />
                  <span className="min-w-0 flex-1 truncate">{entry.query_text}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteEntry.mutate(entry.query_text);
                    }}
                    aria-label={`Remove "${entry.query_text}" from history`}
                    className="shrink-0 rounded p-0.5 text-text-muted opacity-0 transition-opacity hover:text-ds-error group-data-[selected=true]:opacity-100"
                  >
                    <X className="size-3.5" />
                  </button>
                </CommandItem>
              ))}
              <CommandItem
                value="clear-recent-searches"
                onSelect={() => clearHistory.mutate()}
                className="text-text-muted"
              >
                <Trash2 className="size-3.5" />
                Clear all recent searches
              </CommandItem>
            </CommandGroup>
          )}

          {query.trim() && search.isPending && (
            <LoadingSpinner size="sm" className="flex items-center justify-center py-8" />
          )}

          {query.trim() && hasResults && !search.isPending && (
            <>
              {(search.data!.summary_hits?.length ?? 0) > 0 && (
                <CommandGroup heading="Documents & Pages">
                  {(search.data!.summary_hits as SummaryHit[]).map((h) => {
                    const href =
                      h.entity_type === "artifact"
                        ? `/${workspace}/documents/${h.artifact_id}`
                        : `/${workspace}/documents/${h.artifact_id}/pages/${h.entity_id}`;
                    return (
                      <CommandItem
                        key={`summary-${h.entity_id}`}
                        value={`summary-${h.entity_id}`}
                        onSelect={() => handleResultSelect(href)}
                        className="items-start gap-3 py-2.5"
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
                        <EntityTypeBadge type={h.entity_type} className="shrink-0" />
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              )}

              {(search.data!.chunk_hits?.length ?? 0) > 0 && (
                <CommandGroup heading="Text Matches">
                  {(search.data!.chunk_hits as ChunkHit[]).map((c) => {
                    const href = `/${workspace}/documents/${c.artifact_id}/pages/${c.page_id}`;
                    return (
                      <CommandItem
                        key={`chunk-${c.page_id}-${c.score}`}
                        value={`chunk-${c.page_id}-${c.score}`}
                        onSelect={() => handleResultSelect(href)}
                        className="items-start gap-3 py-2.5"
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
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              )}

              <CommandItem
                value="view-all-results"
                onSelect={handleViewAll}
                className="justify-center text-xs font-medium text-accent-text"
              >
                View all results
                <ArrowRight className="size-3" />
              </CommandItem>
            </>
          )}

          {!search.isPending && (
            <CommandEmpty>
              {search.isError
                ? "Search failed. Is the backend running?"
                : query.trim()
                  ? `No results found for "${query.trim()}"`
                  : "No recent searches yet."}
            </CommandEmpty>
          )}
        </CommandList>
      </CommandDialog>
    </>
  );
}
