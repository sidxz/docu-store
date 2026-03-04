"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Button } from "primereact/button";
import { Card } from "primereact/card";
import { InputText } from "primereact/inputtext";
import { ProgressSpinner } from "primereact/progressspinner";
import { SelectButton } from "primereact/selectbutton";
import { Tag } from "primereact/tag";

import {
  useSearchPages,
  useSearchSummaries,
  useHierarchicalSearch,
} from "@/hooks/use-search";

type SearchMode = "text" | "summary" | "hierarchical";

const SEARCH_MODES = [
  { label: "Text Chunks", value: "text" as const },
  { label: "Summaries", value: "summary" as const },
  { label: "Hierarchical", value: "hierarchical" as const },
];

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 rounded-full bg-gray-200">
        <div
          className="h-2 rounded-full bg-blue-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-500">{pct}%</span>
    </div>
  );
}

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
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Search</h1>
      <p className="mt-1 text-sm text-gray-500">
        Semantic search across documents, summaries, and compounds.
      </p>

      {/* Search controls */}
      <div className="mt-6 space-y-4">
        <div className="flex gap-3">
          <div className="flex-1">
            <InputText
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter search query..."
              className="w-full"
            />
          </div>
          <Button
            label="Search"
            icon="pi pi-search"
            onClick={handleSearch}
            loading={isPending}
            disabled={!query.trim()}
          />
        </div>

        <SelectButton
          value={mode}
          onChange={(e) => {
            if (e.value) setMode(e.value);
          }}
          options={SEARCH_MODES}
          optionLabel="label"
          optionValue="value"
        />
      </div>

      {/* Loading */}
      {isPending && (
        <div className="mt-8 flex items-center justify-center">
          <ProgressSpinner style={{ width: "40px", height: "40px" }} />
        </div>
      )}

      {/* Text search results */}
      {mode === "text" && textSearch.data && !textSearch.isPending && (
        <TextSearchResults
          data={textSearch.data}
          workspace={workspace}
        />
      )}

      {/* Summary search results */}
      {mode === "summary" && summarySearch.data && !summarySearch.isPending && (
        <SummarySearchResults
          data={summarySearch.data}
          workspace={workspace}
        />
      )}

      {/* Hierarchical search results */}
      {mode === "hierarchical" &&
        hierarchicalSearch.data &&
        !hierarchicalSearch.isPending && (
          <HierarchicalSearchResults
            data={hierarchicalSearch.data}
            workspace={workspace}
          />
        )}

      {/* Error states */}
      {(textSearch.error || summarySearch.error || hierarchicalSearch.error) && (
        <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Search failed. Please check that the backend is running and try again.
        </div>
      )}
    </div>
  );
}

/* ─── Text chunk results ────────────────────────────────────── */

function TextSearchResults({
  data,
  workspace,
}: {
  data: {
    query: string;
    results: {
      page_id: string;
      artifact_id: string;
      page_index: number;
      similarity_score: number;
      text_preview?: string | null;
      artifact_name?: string | null;
    }[];
    total_results: number;
    model_used: string;
  };
  workspace: string;
}) {
  return (
    <div className="mt-6">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {data.total_results} result{data.total_results !== 1 ? "s" : ""} for{" "}
          <span className="font-medium text-gray-700">
            &ldquo;{data.query}&rdquo;
          </span>
        </p>
        <span className="text-xs text-gray-400">Model: {data.model_used}</span>
      </div>

      <div className="space-y-3">
        {data.results.map((r) => (
          <Card key={`${r.page_id}-${r.similarity_score}`} className="shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Link
                    href={`/${workspace}/documents/${r.artifact_id}/pages/${r.page_id}`}
                    className="text-sm font-medium text-blue-600 hover:underline"
                  >
                    {r.artifact_name ?? "Untitled"} — Page {r.page_index}
                  </Link>
                </div>
                {r.text_preview && (
                  <p className="mt-1 text-sm text-gray-600 line-clamp-3">
                    {r.text_preview}
                  </p>
                )}
                <div className="mt-2 flex items-center gap-3">
                  <Link
                    href={`/${workspace}/documents/${r.artifact_id}`}
                    className="text-xs text-gray-400 hover:text-gray-600"
                  >
                    View artifact
                  </Link>
                </div>
              </div>
              <ScoreBar score={r.similarity_score} />
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ─── Summary search results ────────────────────────────────── */

function SummarySearchResults({
  data,
  workspace,
}: {
  data: {
    query: string;
    results: {
      entity_type: "page" | "artifact";
      entity_id: string;
      artifact_id: string;
      similarity_score: number;
      summary_text?: string | null;
      artifact_title?: string | null;
    }[];
    total_results: number;
    model_used: string;
  };
  workspace: string;
}) {
  return (
    <div className="mt-6">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {data.total_results} result{data.total_results !== 1 ? "s" : ""} for{" "}
          <span className="font-medium text-gray-700">
            &ldquo;{data.query}&rdquo;
          </span>
        </p>
        <span className="text-xs text-gray-400">Model: {data.model_used}</span>
      </div>

      <div className="space-y-3">
        {data.results.map((r) => (
          <Card key={`${r.entity_id}-${r.similarity_score}`} className="shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Tag
                    value={r.entity_type}
                    severity={r.entity_type === "artifact" ? "info" : "secondary"}
                  />
                  <Link
                    href={
                      r.entity_type === "artifact"
                        ? `/${workspace}/documents/${r.artifact_id}`
                        : `/${workspace}/documents/${r.artifact_id}/pages/${r.entity_id}`
                    }
                    className="text-sm font-medium text-blue-600 hover:underline"
                  >
                    {r.artifact_title ?? r.entity_id}
                  </Link>
                </div>
                {r.summary_text && (
                  <p className="mt-1 text-sm text-gray-600 line-clamp-3">
                    {r.summary_text}
                  </p>
                )}
              </div>
              <ScoreBar score={r.similarity_score} />
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ─── Hierarchical search results ───────────────────────────── */

function HierarchicalSearchResults({
  data,
  workspace,
}: {
  data: {
    query: string;
    summary_hits: {
      entity_type: "page" | "artifact";
      entity_id: string;
      artifact_id: string;
      score: number;
      summary_text?: string | null;
      artifact_title?: string | null;
    }[];
    chunk_hits: {
      page_id: string;
      artifact_id: string;
      page_index: number;
      score: number;
      text_preview?: string | null;
    }[];
    total_summary_hits: number;
    total_chunk_hits: number;
    model_used: string;
  };
  workspace: string;
}) {
  return (
    <div className="mt-6">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {data.total_summary_hits} summary hit
          {data.total_summary_hits !== 1 ? "s" : ""},{" "}
          {data.total_chunk_hits} chunk hit
          {data.total_chunk_hits !== 1 ? "s" : ""} for{" "}
          <span className="font-medium text-gray-700">
            &ldquo;{data.query}&rdquo;
          </span>
        </p>
        <span className="text-xs text-gray-400">Model: {data.model_used}</span>
      </div>

      {/* Summary hits */}
      {data.summary_hits.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-medium text-gray-700">
            Summary Matches
          </h2>
          <div className="space-y-3">
            {data.summary_hits.map((h) => (
              <Card key={`${h.entity_id}-${h.score}`} className="shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Tag
                        value={h.entity_type}
                        severity={
                          h.entity_type === "artifact" ? "info" : "secondary"
                        }
                      />
                      <Link
                        href={
                          h.entity_type === "artifact"
                            ? `/${workspace}/documents/${h.artifact_id}`
                            : `/${workspace}/documents/${h.artifact_id}/pages/${h.entity_id}`
                        }
                        className="text-sm font-medium text-blue-600 hover:underline"
                      >
                        {h.artifact_title ?? h.entity_id}
                      </Link>
                    </div>
                    {h.summary_text && (
                      <p className="mt-1 text-sm text-gray-600 line-clamp-3">
                        {h.summary_text}
                      </p>
                    )}
                  </div>
                  <ScoreBar score={h.score} />
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Chunk hits */}
      {data.chunk_hits.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-medium text-gray-700">
            Text Chunk Matches
          </h2>
          <div className="space-y-3">
            {data.chunk_hits.map((c) => (
              <Card key={`${c.page_id}-${c.score}`} className="shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <Link
                      href={`/${workspace}/documents/${c.artifact_id}/pages/${c.page_id}`}
                      className="text-sm font-medium text-blue-600 hover:underline"
                    >
                      Page {c.page_index}
                    </Link>
                    {c.text_preview && (
                      <p className="mt-1 text-sm text-gray-600 line-clamp-3">
                        {c.text_preview}
                      </p>
                    )}
                    <Link
                      href={`/${workspace}/documents/${c.artifact_id}`}
                      className="mt-1 text-xs text-gray-400 hover:text-gray-600"
                    >
                      View artifact
                    </Link>
                  </div>
                  <ScoreBar score={c.score} />
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
