"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Search as SearchIcon,
  X,
  Trash2,
  Clock,
  Loader2,
  AlertCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { TextSearchResults } from "@/components/search/TextSearchResults";
import { SummarySearchResults } from "@/components/search/SummarySearchResults";
import { HierarchicalSearchResults } from "@/components/search/HierarchicalSearchResults";
import { TagFilter } from "@/components/search/TagFilter";
import {
  useTextSearchQuery,
  useSummarySearchQuery,
  useHierarchicalSearchQuery,
} from "@/hooks/use-search";
import {
  useRecentSearches,
  useDeleteSearchEntry,
  useClearSearchHistory,
} from "@/hooks/use-activity";
import { authFetch } from "@/lib/auth-fetch";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { useAnalytics } from "@/hooks/use-analytics";

type SearchMode = "text" | "summary" | "hierarchical";

const SEARCH_MODES = [
  { label: "Exact Match", value: "text" as SearchMode },
  { label: "Overview Search", value: "summary" as SearchMode },
  { label: "Deep Search", value: "hierarchical" as SearchMode },
];

export default function SearchPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();

  // ── Read state from URL ──────────────────────────────────────────────────
  const urlQuery = searchParams.get("q") ?? "";
  const urlMode = (searchParams.get("mode") ?? "hierarchical") as SearchMode;
  const urlTags = searchParams.get("tags")?.split(",").filter(Boolean) ?? [];
  const urlTagMatch = (searchParams.get("match") ?? "any") as "any" | "all";

  // ── Local input state (what user is currently typing) ────────────────────
  const [inputValue, setInputValue] = useState(urlQuery);
  const [localMode, setLocalMode] = useState<SearchMode>(urlMode);
  const [filterTags, setFilterTags] = useState<string[]>(urlTags);
  const [tagMatchMode, setTagMatchMode] = useState<"any" | "all">(urlTagMatch);
  const [showSuggestions, setShowSuggestions] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const suggestionsRef = useRef<HTMLDivElement>(null);

  // Sync input with URL when URL changes (e.g. back button)
  const urlTagsStr = searchParams.get("tags") ?? "";
  useEffect(() => {
    setInputValue(urlQuery);
    setLocalMode(urlMode);
    setFilterTags(urlTags);
    setTagMatchMode(urlTagMatch);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlQuery, urlMode, urlTagsStr, urlTagMatch]);

  // ── Search history ───────────────────────────────────────────────────────
  const { data: recentSearches } = useRecentSearches(15);
  const deleteEntry = useDeleteSearchEntry();
  const clearHistory = useClearSearchHistory();

  // Filter suggestions by what user is typing
  const filteredSuggestions = recentSearches?.filter(
    (e) =>
      !inputValue.trim() ||
      e.query_text.toLowerCase().includes(inputValue.trim().toLowerCase()),
  );

  // Close suggestions on click outside
  useEffect(() => {
    if (!showSuggestions) return;
    const handler = (e: MouseEvent) => {
      if (
        suggestionsRef.current &&
        !suggestionsRef.current.contains(e.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(e.target as Node)
      ) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showSuggestions]);

  // ── Build params for active search mode (null = disabled) ────────────────
  const tagParams = urlTags.length > 0
    ? { tags: urlTags, tag_match_mode: urlTagMatch }
    : {};

  const textSearch = useTextSearchQuery(
    urlMode === "text" && urlQuery
      ? { query_text: urlQuery, ...tagParams }
      : null,
  );
  const summarySearch = useSummarySearchQuery(
    urlMode === "summary" && urlQuery
      ? { query_text: urlQuery, ...tagParams }
      : null,
  );
  const hierarchicalSearch = useHierarchicalSearchQuery(
    urlMode === "hierarchical" && urlQuery
      ? { query_text: urlQuery, include_chunks: true, ...tagParams }
      : null,
  );

  // ── Activity tracking: record search after results arrive ────────────────
  const lastRecordedQuery = useRef("");
  useEffect(() => {
    const activeData =
      (urlMode === "text" && textSearch.data) ||
      (urlMode === "summary" && summarySearch.data) ||
      (urlMode === "hierarchical" && hierarchicalSearch.data);

    if (activeData && urlQuery && urlQuery !== lastRecordedQuery.current) {
      lastRecordedQuery.current = urlQuery;
      authFetch("/user/activity/search", {
        method: "POST",
        body: JSON.stringify({
          query_text: urlQuery,
          search_mode: urlMode,
        }),
        headers: { "Content-Type": "application/json" },
      }).catch(() => {});
    }
  }, [urlQuery, urlMode, textSearch.data, summarySearch.data, hierarchicalSearch.data]);

  // ── URL navigation helpers ───────────────────────────────────────────────

  const executeSearch = (query: string, mode?: SearchMode) => {
    const trimmed = query.trim();
    if (!trimmed) return;
    setShowSuggestions(false);
    const params = new URLSearchParams();
    params.set("q", trimmed);
    const m = mode ?? localMode;
    if (m !== "hierarchical") params.set("mode", m);
    if (filterTags.length) params.set("tags", filterTags.join(","));
    if (tagMatchMode !== "any") params.set("match", tagMatchMode);
    router.push(`/${workspace}/search?${params.toString()}`);
  };

  const handleSearch = () => executeSearch(inputValue);

  const updateUrlParams = (overrides: { mode?: SearchMode; tags?: string[]; match?: string }) => {
    if (!urlQuery) return;
    const params = new URLSearchParams(searchParams.toString());
    if (overrides.mode !== undefined) {
      if (overrides.mode === "hierarchical") params.delete("mode");
      else params.set("mode", overrides.mode);
    }
    if (overrides.tags !== undefined) {
      if (overrides.tags.length) params.set("tags", overrides.tags.join(","));
      else params.delete("tags");
    }
    if (overrides.match !== undefined) {
      if (overrides.match === "any") params.delete("match");
      else params.set("match", overrides.match);
    }
    router.replace(`/${workspace}/search?${params.toString()}`);
  };

  const { trackEvent } = useAnalytics();

  const handleModeChange = (newMode: SearchMode) => {
    trackEvent("search_tab_switched", {
      from_tab: localMode,
      to_tab: newMode,
      had_results: (textSearch.data || summarySearch.data || hierarchicalSearch.data) ? 1 : 0,
    });
    setLocalMode(newMode);
    updateUrlParams({ mode: newMode });
  };

  const handleTagsChange = (tags: string[]) => {
    setFilterTags(tags);
    updateUrlParams({ tags });
  };

  const handleTagMatchChange = (match: "any" | "all") => {
    setTagMatchMode(match);
    updateUrlParams({ match });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSearch();
    } else if (e.key === "Escape") {
      setShowSuggestions(false);
    }
  };

  // isFetching = actual network request in progress.
  // isPending would be wrong here: disabled queries (inactive modes) are permanently "pending".
  const isFetching =
    textSearch.isFetching ||
    summarySearch.isFetching ||
    hierarchicalSearch.isFetching;

  const isLoading = urlQuery ? isFetching : false;

  const hasResults =
    (urlMode === "text" && textSearch.data) ||
    (urlMode === "summary" && summarySearch.data) ||
    (urlMode === "hierarchical" && hierarchicalSearch.data);

  const hasSuggestions = filteredSuggestions && filteredSuggestions.length > 0;

  return (
    <div>
      <PageHeader
        icon={SearchIcon}
        title="Search"
        subtitle="Semantic search across documents, summaries, and compounds"
      />

      {/* Search controls */}
      <div className="space-y-4">
        <div className="flex gap-3">
          {/* Search input with autocomplete */}
          <div className="relative flex-1">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted">
                <SearchIcon className="h-4 w-4" />
              </span>
              <input
                ref={inputRef}
                value={inputValue}
                onChange={(e) => {
                  setInputValue(e.target.value);
                  setShowSuggestions(true);
                }}
                onFocus={() => setShowSuggestions(true)}
                onKeyDown={handleKeyDown}
                placeholder="Enter search query..."
                className="w-full rounded-md border border-border-default bg-surface py-2 pl-10 pr-3 text-sm text-text-primary placeholder:text-text-muted outline-none transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              />
            </div>

            {/* Suggestions dropdown */}
            {showSuggestions && hasSuggestions && (
              <div
                ref={suggestionsRef}
                className="absolute left-0 right-0 top-full z-50 mt-1 max-h-72 overflow-y-auto rounded-lg border border-border-default bg-surface-elevated/60 shadow-ds-md backdrop-blur-2xl"
              >
                {/* Header with clear all */}
                <div className="flex items-center justify-between border-b border-border-subtle px-3 py-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Recent Searches
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      clearHistory.mutate();
                    }}
                    className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-text-muted transition-colors hover:bg-ds-error/10 hover:text-ds-error"
                  >
                    <Trash2 className="h-3 w-3" />
                    Clear all
                  </button>
                </div>

                {/* Suggestion items */}
                {filteredSuggestions!.map((entry, i) => (
                  <div
                    key={`${entry.query_text}-${i}`}
                    className="group flex items-center gap-2 px-3 py-2 transition-colors hover:bg-surface-sunken"
                  >
                    <Clock className="h-3.5 w-3.5 shrink-0 text-text-muted" />
                    <button
                      className="min-w-0 flex-1 truncate text-left text-sm text-text-primary"
                      onClick={() => {
                        setInputValue(entry.query_text);
                        executeSearch(entry.query_text, entry.search_mode as SearchMode);
                      }}
                    >
                      {entry.query_text}
                    </button>
                    <span className="shrink-0 text-xs text-text-muted">
                      {entry.search_mode === "hierarchical" ? "deep" : entry.search_mode}
                    </span>
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
              </div>
            )}
          </div>

          <Button onClick={handleSearch} disabled={!inputValue.trim() || isLoading}>
            {isLoading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <SearchIcon className="size-4" />
            )}
            Search
          </Button>
        </div>

        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={localMode}
          onValueChange={(nv) => nv && handleModeChange(nv as SearchMode)}
        >
          {SEARCH_MODES.map((o) => (
            <ToggleGroupItem key={o.value} value={o.value}>
              {o.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        <TagFilter
          tags={filterTags}
          matchMode={tagMatchMode}
          onTagsChange={handleTagsChange}
          onMatchModeChange={handleTagMatchChange}
        />
      </div>

      {/* Results */}
      {urlMode === "text" && textSearch.data && !textSearch.isFetching && (
        <TextSearchResults data={textSearch.data} workspace={workspace} />
      )}

      {urlMode === "summary" && summarySearch.data && !summarySearch.isFetching && (
        <SummarySearchResults data={summarySearch.data} workspace={workspace} />
      )}

      {urlMode === "hierarchical" &&
        hierarchicalSearch.data &&
        !hierarchicalSearch.isFetching && (
          <HierarchicalSearchResults
            data={hierarchicalSearch.data}
            workspace={workspace}
          />
        )}

      {isLoading && (
        <LoadingSpinner size="sm" className="mt-12 flex items-center justify-center" />
      )}

      {!hasResults && !isLoading && (
        <EmptyState
          icon={SearchIcon}
          title="Search your documents"
          description="Enter a query above to find relevant content across your documents, summaries, and text chunks."
        />
      )}

      {(textSearch.error || summarySearch.error || hierarchicalSearch.error) && (
        <div className="mt-6">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              Search failed. Please check that the backend is running and try again.
            </AlertDescription>
          </Alert>
        </div>
      )}
    </div>
  );
}
