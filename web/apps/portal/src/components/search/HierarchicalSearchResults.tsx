import { SearchResultCard } from "./SearchResultCard";
import { API_URL } from "@/lib/constants";

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
  artifact_name?: string | null;
  page_name?: string | null;
  rerank_score?: number | null;
  original_rank?: number | null;
}

interface RerankInfo {
  reranker_model: string;
  candidates_before: number;
  results_after: number;
  top_promotion?: number | null;
}

interface HierarchicalSearchResultsProps {
  data: {
    query: string;
    summary_hits: SummaryHit[];
    chunk_hits: ChunkHit[];
    total_summary_hits: number;
    total_chunk_hits: number;
    model_used: string;
    chunk_rerank_info?: RerankInfo | null;
  };
  workspace: string;
}

export function HierarchicalSearchResults({
  data,
  workspace,
}: HierarchicalSearchResultsProps) {
  return (
    <div className="mt-6">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-text-secondary">
          {data.total_summary_hits} summary hit
          {data.total_summary_hits !== 1 ? "s" : ""},{" "}
          {data.total_chunk_hits} chunk hit
          {data.total_chunk_hits !== 1 ? "s" : ""} for{" "}
          <span className="font-medium text-text-primary">
            &ldquo;{data.query}&rdquo;
          </span>
        </p>
        <span className="text-xs text-text-muted">
          Model: {data.model_used}
        </span>
      </div>

      {/* Summary hits */}
      {data.summary_hits.length > 0 && (
        <div className="mb-6">
          <h3 className="mb-2 text-sm font-medium text-text-secondary">
            Summary Matches
          </h3>
          <div className="space-y-3">
            {data.summary_hits.map((h) => (
              <SearchResultCard
                key={`${h.entity_id}-${h.score}`}
                title={
                  h.entity_type === "page" && h.artifact_title
                    ? `${h.artifact_title} | Page ${(h.page_index ?? 0) + 1}`
                    : h.artifact_title ?? h.entity_id.slice(0, 8)
                }
                href={
                  h.entity_type === "artifact"
                    ? `/${workspace}/documents/${h.artifact_id}`
                    : `/${workspace}/documents/${h.artifact_id}/pages/${h.entity_id}`
                }
                score={h.score}
                preview={h.summary_text}
                entityType={h.entity_type}
                thumbnailSrc={`${API_URL}/artifacts/${h.artifact_id}/pages/${h.page_index ?? 0}/image`}
              />
            ))}
          </div>
        </div>
      )}

      {/* Chunk hits */}
      {data.chunk_hits.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-text-secondary">
            Exact Matches
          </h3>

          {data.chunk_rerank_info && (
            <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs dark:border-blue-800 dark:bg-blue-950">
              <span className="font-medium text-blue-700 dark:text-blue-300">Reranked</span>
              <span className="ml-2 text-blue-600 dark:text-blue-400">
                {data.chunk_rerank_info.candidates_before} candidates → {data.chunk_rerank_info.results_after} results
                {data.chunk_rerank_info.top_promotion != null && data.chunk_rerank_info.top_promotion > 0 && (
                  <> · top result promoted {data.chunk_rerank_info.top_promotion} positions</>
                )}
                <span className="ml-2 opacity-60">({data.chunk_rerank_info.reranker_model})</span>
              </span>
            </div>
          )}

          <div className="space-y-3">
            {data.chunk_hits.map((c) => (
              <SearchResultCard
                key={`${c.page_id}-${c.score}`}
                title={
                  c.artifact_name
                    ? `${c.artifact_name} | ${c.page_name ?? `Page ${c.page_index + 1}`}`
                    : c.page_name ?? `Page ${c.page_index + 1}`
                }
                href={`/${workspace}/documents/${c.artifact_id}/pages/${c.page_id}`}
                score={c.score}
                preview={c.text_preview}
                thumbnailSrc={`${API_URL}/artifacts/${c.artifact_id}/pages/${c.page_index}/image`}
                secondaryLink={{
                  label: "View document",
                  href: `/${workspace}/documents/${c.artifact_id}`,
                }}
              >
                {c.rerank_score != null && (
                  <div className="mt-1.5 flex items-center gap-2 text-xs text-text-muted">
                    <span>vector: {c.score.toFixed(3)}</span>
                    <span>→ rerank: {c.rerank_score.toFixed(3)}</span>
                    {c.original_rank != null && (
                      <span className={
                        c.original_rank > 0
                          ? "text-green-600 dark:text-green-400"
                          : "text-text-muted"
                      }>
                        {c.original_rank > 0 ? `↑${c.original_rank}` : "—"}
                      </span>
                    )}
                  </div>
                )}
              </SearchResultCard>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
