import { SearchResultCard } from "./SearchResultCard";

interface SummaryResult {
  entity_type: "page" | "artifact";
  entity_id: string;
  artifact_id: string;
  similarity_score: number;
  summary_text?: string | null;
  artifact_title?: string | null;
}

interface SummarySearchResultsProps {
  data: {
    query: string;
    results: SummaryResult[];
    total_results: number;
    model_used: string;
  };
  workspace: string;
}

export function SummarySearchResults({
  data,
  workspace,
}: SummarySearchResultsProps) {
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

      <div className="space-y-3">
        {data.results.map((r) => (
          <SearchResultCard
            key={`${r.entity_id}-${r.similarity_score}`}
            title={r.artifact_title ?? r.entity_id}
            href={
              r.entity_type === "artifact"
                ? `/${workspace}/documents/${r.artifact_id}`
                : `/${workspace}/documents/${r.artifact_id}/pages/${r.entity_id}`
            }
            score={r.similarity_score}
            preview={r.summary_text}
            entityType={r.entity_type}
          />
        ))}
      </div>
    </div>
  );
}
