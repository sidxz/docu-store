import { SearchResultCard } from "./SearchResultCard";
import { API_URL } from "@/lib/constants";

interface TextResult {
  page_id: string;
  artifact_id: string;
  page_index: number;
  similarity_score: number;
  rerank_score?: number | null;
  original_rank?: number | null;
  text_preview?: string | null;
  artifact_name?: string | null;
}

interface RerankInfo {
  reranker_model: string;
  candidates_before: number;
  results_after: number;
  top_promotion?: number | null;
}

interface TextSearchResultsProps {
  data: {
    query: string;
    results: TextResult[];
    total_results: number;
    model_used: string;
    rerank_info?: RerankInfo | null;
  };
  workspace: string;
}

export function TextSearchResults({ data, workspace }: TextSearchResultsProps) {
  return (
    <div className="mt-6">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-text-secondary">
          {data.total_results} result{data.total_results !== 1 ? "s" : ""} for{" "}
          <span className="font-medium text-text-primary">
            &ldquo;{data.query}&rdquo;
          </span>
        </p>
        <span className="text-xs text-text-muted">
          Model: {data.model_used}
        </span>
      </div>

      {data.rerank_info && (
        <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs dark:border-blue-800 dark:bg-blue-950">
          <span className="font-medium text-blue-700 dark:text-blue-300">Reranked</span>
          <span className="ml-2 text-blue-600 dark:text-blue-400">
            {data.rerank_info.candidates_before} candidates → {data.rerank_info.results_after} results
            {data.rerank_info.top_promotion != null && data.rerank_info.top_promotion > 0 && (
              <> · top result promoted {data.rerank_info.top_promotion} positions</>
            )}
            <span className="ml-2 opacity-60">({data.rerank_info.reranker_model})</span>
          </span>
        </div>
      )}

      <div className="space-y-3">
        {data.results.map((r) => (
          <SearchResultCard
            key={`${r.page_id}-${r.similarity_score}`}
            title={`${r.artifact_name ?? "Untitled"} — Page ${r.page_index}`}
            href={`/${workspace}/documents/${r.artifact_id}/pages/${r.page_id}`}
            score={r.similarity_score}
            preview={r.text_preview}
            thumbnailSrc={`${API_URL}/artifacts/${r.artifact_id}/pages/${r.page_index}/image`}
            secondaryLink={{
              label: "View document",
              href: `/${workspace}/documents/${r.artifact_id}`,
            }}
          >
            {r.rerank_score != null && (
              <div className="mt-1.5 flex items-center gap-2 text-xs text-text-muted">
                <span>vector: {r.similarity_score.toFixed(3)}</span>
                <span>→ rerank: {r.rerank_score.toFixed(3)}</span>
                {r.original_rank != null && (
                  <span className={
                    r.original_rank > 0
                      ? "text-green-600 dark:text-green-400"
                      : "text-text-muted"
                  }>
                    {r.original_rank > 0 ? `↑${r.original_rank}` : "—"}
                  </span>
                )}
              </div>
            )}
          </SearchResultCard>
        ))}
      </div>
    </div>
  );
}
