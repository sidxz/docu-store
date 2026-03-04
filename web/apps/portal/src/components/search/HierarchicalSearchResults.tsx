import { SearchResultCard } from "./SearchResultCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

interface HierarchicalSearchResultsProps {
  data: {
    query: string;
    summary_hits: SummaryHit[];
    chunk_hits: ChunkHit[];
    total_summary_hits: number;
    total_chunk_hits: number;
    model_used: string;
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
                title={h.artifact_title ?? h.entity_id}
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
            Text Chunk Matches
          </h3>
          <div className="space-y-3">
            {data.chunk_hits.map((c) => (
              <SearchResultCard
                key={`${c.page_id}-${c.score}`}
                title={`Page ${c.page_index}`}
                href={`/${workspace}/documents/${c.artifact_id}/pages/${c.page_id}`}
                score={c.score}
                preview={c.text_preview}
                thumbnailSrc={`${API_URL}/artifacts/${c.artifact_id}/pages/${c.page_index}/image`}
                secondaryLink={{
                  label: "View document",
                  href: `/${workspace}/documents/${c.artifact_id}`,
                }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
