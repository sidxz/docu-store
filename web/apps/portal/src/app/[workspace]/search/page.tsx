"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Search as SearchIcon } from "lucide-react";
import { Button } from "primereact/button";
import { IconField } from "primereact/iconfield";
import { InputIcon } from "primereact/inputicon";
import { InputText } from "primereact/inputtext";
import { Message } from "primereact/message";
import { SelectButton } from "primereact/selectbutton";

import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { TextSearchResults } from "@/components/search/TextSearchResults";
import { SummarySearchResults } from "@/components/search/SummarySearchResults";
import { HierarchicalSearchResults } from "@/components/search/HierarchicalSearchResults";
import { TagFilter } from "@/components/search/TagFilter";
import {
  useSearchPages,
  useSearchSummaries,
  useHierarchicalSearch,
} from "@/hooks/use-search";
import { useSearchStore } from "@/lib/stores/search-store";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";

type SearchMode = "text" | "summary" | "hierarchical";

const SEARCH_MODES = [
  { label: "Exact Match", value: "text" as SearchMode },
  { label: "Overview Search", value: "summary" as SearchMode },
  { label: "Deep Search", value: "hierarchical" as SearchMode },
];

export default function SearchPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("hierarchical");
  const [filterTags, setFilterTags] = useState<string[]>([]);
  const [tagMatchMode, setTagMatchMode] = useState<"any" | "all">("any");

  // Track whether we need to auto-search after prefill
  const [shouldAutoSearch, setShouldAutoSearch] = useState(false);

  const textSearch = useSearchPages();
  const summarySearch = useSearchSummaries();
  const hierarchicalSearch = useHierarchicalSearch();

  // Step 1: Consume pending query from store on mount — only prefill state
  useEffect(() => {
    const pending = useSearchStore.getState().pendingQuery;
    if (pending) {
      useSearchStore.getState().setPendingQuery(null);
      setQuery(pending);
      setMode("hierarchical");
      setShouldAutoSearch(true);
    }
  }, []);

  // Step 2: Fire the search AFTER the query state has been committed
  // This runs on the render AFTER setQuery/setShouldAutoSearch
  useEffect(() => {
    if (shouldAutoSearch && query) {
      setShouldAutoSearch(false);
      hierarchicalSearch.mutate({ query_text: query, include_chunks: true, ...tagParams });
    }
  }, [shouldAutoSearch, query]); // eslint-disable-line react-hooks/exhaustive-deps

  const isPending =
    textSearch.isPending ||
    summarySearch.isPending ||
    hierarchicalSearch.isPending;

  const hasResults =
    (mode === "text" && textSearch.data) ||
    (mode === "summary" && summarySearch.data) ||
    (mode === "hierarchical" && hierarchicalSearch.data);

  const tagParams = filterTags.length > 0
    ? { tags: filterTags, tag_match_mode: tagMatchMode as "any" | "all" }
    : {};

  const handleSearch = () => {
    const trimmed = query.trim();
    if (!trimmed) return;

    if (mode === "text") {
      textSearch.mutate({ query_text: trimmed, ...tagParams });
    } else if (mode === "summary") {
      summarySearch.mutate({ query_text: trimmed, ...tagParams });
    } else {
      hierarchicalSearch.mutate({ query_text: trimmed, include_chunks: true, ...tagParams });
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
        <div className="flex gap-3">
          <IconField iconPosition="left" className="flex-1">
            <InputIcon className="pi pi-search" />
            <InputText
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter search query..."
              className="w-full"
            />
          </IconField>
          <Button
            label="Search"
            icon={isPending ? "pi pi-spin pi-spinner" : "pi pi-search"}
            onClick={handleSearch}
            disabled={!query.trim() || isPending}
          />
        </div>

        <SelectButton
          value={mode}
          options={SEARCH_MODES}
          onChange={(e) => {
            if (e.value) setMode(e.value);
          }}
        />

        <TagFilter
          tags={filterTags}
          matchMode={tagMatchMode}
          onTagsChange={setFilterTags}
          onMatchModeChange={setTagMatchMode}
        />
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

      {isPending && (
        <LoadingSpinner size="sm" className="mt-12 flex items-center justify-center" />
      )}

      {!hasResults && !isPending && (
        <EmptyState
          icon={SearchIcon}
          title="Search your documents"
          description="Enter a query above to find relevant content across your documents, summaries, and text chunks."
        />
      )}

      {(textSearch.error || summarySearch.error || hierarchicalSearch.error) && (
        <div className="mt-6">
          <Message
            severity="error"
            text="Search failed. Please check that the backend is running and try again."
          />
        </div>
      )}
    </div>
  );
}
