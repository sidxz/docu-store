"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { Search as SearchIcon, Loader2 } from "lucide-react";

import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { TextSearchResults } from "@/components/search/TextSearchResults";
import { SummarySearchResults } from "@/components/search/SummarySearchResults";
import { HierarchicalSearchResults } from "@/components/search/HierarchicalSearchResults";
import {
  useSearchPages,
  useSearchSummaries,
  useHierarchicalSearch,
} from "@/hooks/use-search";

type SearchMode = "text" | "summary" | "hierarchical";

const SEARCH_MODES: { label: string; value: SearchMode }[] = [
  { label: "Text Chunks", value: "text" },
  { label: "Summaries", value: "summary" },
  { label: "Hierarchical", value: "hierarchical" },
];

export default function SearchPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("hierarchical");

  const textSearch = useSearchPages();
  const summarySearch = useSearchSummaries();
  const hierarchicalSearch = useHierarchicalSearch();

  const isPending =
    textSearch.isPending ||
    summarySearch.isPending ||
    hierarchicalSearch.isPending;

  const hasResults =
    (mode === "text" && textSearch.data) ||
    (mode === "summary" && summarySearch.data) ||
    (mode === "hierarchical" && hierarchicalSearch.data);

  const handleSearch = () => {
    const trimmed = query.trim();
    if (!trimmed) return;

    if (mode === "text") {
      textSearch.mutate({ query_text: trimmed });
    } else if (mode === "summary") {
      summarySearch.mutate({ query_text: trimmed });
    } else {
      hierarchicalSearch.mutate({ query_text: trimmed, include_chunks: true });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  return (
    <div>
      <PageHeader
        icon={SearchIcon}
        title="Search"
        subtitle="Semantic search across documents, summaries, and compounds"
      />

      {/* Search controls */}
      <div className="space-y-4">
        {/* Search input */}
        <div className="flex gap-3">
          <div className="relative flex-1">
            <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter search query..."
              className="w-full rounded-lg border border-border-default bg-surface-elevated py-2.5 pl-10 pr-4 text-sm text-text-primary placeholder:text-text-muted transition-colors focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={!query.trim() || isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            {isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <SearchIcon className="h-4 w-4" />
            )}
            Search
          </button>
        </div>

        {/* Mode selector — custom segmented control */}
        <div className="inline-flex rounded-lg border border-border-default bg-surface-elevated p-0.5">
          {SEARCH_MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => setMode(m.value)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
                mode === m.value
                  ? "bg-accent text-white shadow-sm"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Results */}
      {mode === "text" && textSearch.data && !textSearch.isPending && (
        <TextSearchResults data={textSearch.data} workspace={workspace} />
      )}

      {mode === "summary" && summarySearch.data && !summarySearch.isPending && (
        <SummarySearchResults data={summarySearch.data} workspace={workspace} />
      )}

      {mode === "hierarchical" &&
        hierarchicalSearch.data &&
        !hierarchicalSearch.isPending && (
          <HierarchicalSearchResults
            data={hierarchicalSearch.data}
            workspace={workspace}
          />
        )}

      {/* Loading */}
      {isPending && (
        <div className="mt-12 flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-accent" />
        </div>
      )}

      {/* Empty state — no search yet */}
      {!hasResults && !isPending && (
        <EmptyState
          icon={SearchIcon}
          title="Search your documents"
          description="Enter a query above to find relevant content across your documents, summaries, and text chunks."
        />
      )}

      {/* Error states */}
      {(textSearch.error || summarySearch.error || hierarchicalSearch.error) && (
        <div className="mt-6 rounded-lg border border-ds-error/20 bg-ds-error/5 p-4 text-sm text-ds-error">
          Search failed. Please check that the backend is running and try again.
        </div>
      )}
    </div>
  );
}
