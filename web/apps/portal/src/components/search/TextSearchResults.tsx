import { SearchResultCard } from "./SearchResultCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface TextResult {
  page_id: string;
  artifact_id: string;
  page_index: number;
  similarity_score: number;
  text_preview?: string | null;
  artifact_name?: string | null;
}

interface TextSearchResultsProps {
  data: {
    query: string;
    results: TextResult[];
    total_results: number;
    model_used: string;
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
          />
        ))}
      </div>
    </div>
  );
}
