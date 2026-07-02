import Link from "next/link";
import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";

import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { AuthThumbnail } from "@/components/ui/TableThumbnail";
import { highlightMatches } from "./highlight-matches";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { API_URL } from "@/lib/constants";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SummaryHit {
  entity_type: "page" | "artifact";
  entity_id: string;
  artifact_id: string;
  score: number;
  summary_text?: string | null;
  artifact_title?: string | null;
  page_index?: number | null;
  authors?: string[];
  presentation_date?: string | null;
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

// ---------------------------------------------------------------------------
// Grouped data structures
// ---------------------------------------------------------------------------

interface PageGroup {
  pageId: string | null;
  pageIndex: number;
  pageName: string | null;
  summary: SummaryHit | null;
  chunk: ChunkHit | null;
  bestScore: number;
  /** Position in the reranked chunk list (0-indexed), for computing displacement */
  chunkRerankPosition: number | null;
}

interface DocumentGroup {
  artifactId: string;
  artifactTitle: string;
  artifactSummary: SummaryHit | null;
  pages: PageGroup[];
  bestScore: number;
  /** Lowest (best) position in the reranked chunk_hits array. null = summary-only group. */
  bestChunkPosition: number | null;
  /** Lowest (best) position in the summary_hits array. null = chunk-only group. */
  bestSummaryRank: number | null;
  /** RRF fusion score — used for document ordering when RRF mode is active. */
  fusionScore: number;
  authors: string[];
  presentationDate: string | null;
}

// ---------------------------------------------------------------------------
// Scoring configuration — tweak these to experiment with ranking behaviour
// ---------------------------------------------------------------------------

interface ScoringConfig {
  /** Ranking strategy: "rrf" (reciprocal rank fusion) or "tiered" (legacy hard tiering) */
  mode: "rrf" | "tiered";
  /** RRF k constant — lower = more aggressive rank separation. Standard: 60. */
  k: number;
  /** Weight for chunk RRF contribution (cross-encoder validated). */
  chunkWeight: number;
  /** Weight for summary RRF contribution. */
  summaryWeight: number;
}

const SCORING_CONFIG: ScoringConfig = {
  mode: "rrf",
  k: 60,
  chunkWeight: 1.0,
  summaryWeight: 1.0,
};

function computeFusionScore(
  bestChunkPosition: number | null,
  bestSummaryRank: number | null,
  config: ScoringConfig = SCORING_CONFIG,
): number {
  const { k, chunkWeight, summaryWeight } = config;
  const chunkRRF = bestChunkPosition !== null ? 1 / (k + bestChunkPosition) : 0;
  const summaryRRF = bestSummaryRank !== null ? 1 / (k + bestSummaryRank) : 0;
  return chunkWeight * chunkRRF + summaryWeight * summaryRRF;
}

function buildDocumentGroups(
  summaryHits: SummaryHit[],
  chunkHits: ChunkHit[],
  config: ScoringConfig = SCORING_CONFIG,
): DocumentGroup[] {
  const groups = new Map<string, DocumentGroup>();

  const getOrCreate = (artifactId: string, title: string): DocumentGroup => {
    let g = groups.get(artifactId);
    if (!g) {
      g = {
        artifactId,
        artifactTitle: title,
        artifactSummary: null,
        pages: [],
        bestScore: 0,
        bestChunkPosition: null,
        bestSummaryRank: null,
        fusionScore: 0,
        authors: [],
        presentationDate: null,
      };
      groups.set(artifactId, g);
    }
    if (title && (!g.artifactTitle || g.artifactTitle === artifactId.slice(0, 8))) {
      g.artifactTitle = title;
    }
    return g;
  };

  // Index page-level summaries by entity_id for correlation
  const pageSummaryMap = new Map<string, SummaryHit>();

  for (let i = 0; i < summaryHits.length; i++) {
    const sh = summaryHits[i];
    const g = getOrCreate(sh.artifact_id, sh.artifact_title ?? "");

    // Track best summary rank per document (array index = rank)
    if (g.bestSummaryRank === null || i < g.bestSummaryRank) {
      g.bestSummaryRank = i;
    }

    if (sh.entity_type === "artifact") {
      g.artifactSummary = sh;
      g.bestScore = Math.max(g.bestScore, sh.score);
      if (sh.authors?.length) g.authors = sh.authors;
      if (sh.presentation_date) g.presentationDate = sh.presentation_date;
    } else {
      // Fallback: use page-level summary metadata if no artifact-level yet
      if (!g.authors.length && sh.authors?.length) g.authors = sh.authors;
      if (!g.presentationDate && sh.presentation_date) g.presentationDate = sh.presentation_date;
      pageSummaryMap.set(sh.entity_id, sh);
    }
  }

  // Build page groups from chunks, correlating with summaries
  const usedSummaryIds = new Set<string>();

  for (let i = 0; i < chunkHits.length; i++) {
    const ch = chunkHits[i];
    const g = getOrCreate(ch.artifact_id, ch.artifact_name ?? "");
    const matchedSummary = pageSummaryMap.get(ch.page_id) ?? null;
    if (matchedSummary) usedSummaryIds.add(matchedSummary.entity_id);

    const bestScore = Math.max(
      ch.score,
      matchedSummary?.score ?? 0,
    );

    g.pages.push({
      pageId: ch.page_id,
      pageIndex: ch.page_index,
      pageName: ch.page_name ?? null,
      summary: matchedSummary,
      chunk: ch,
      bestScore,
      chunkRerankPosition: ch.original_rank != null ? i : null,
    });
    g.bestScore = Math.max(g.bestScore, bestScore);
    if (g.bestChunkPosition === null || i < g.bestChunkPosition) {
      g.bestChunkPosition = i;
    }
  }

  // Add page-level summaries that had no matching chunk
  for (const sh of summaryHits) {
    if (sh.entity_type === "page" && !usedSummaryIds.has(sh.entity_id)) {
      const g = getOrCreate(sh.artifact_id, sh.artifact_title ?? "");
      g.pages.push({
        pageId: sh.entity_id,
        pageIndex: sh.page_index ?? 0,
        pageName: null,
        summary: sh,
        chunk: null,
        bestScore: sh.score,
        chunkRerankPosition: null,
      });
      g.bestScore = Math.max(g.bestScore, sh.score);
    }
  }

  // Compute fusion scores for all groups
  for (const g of groups.values()) {
    g.fusionScore = computeFusionScore(g.bestChunkPosition, g.bestSummaryRank, config);
  }

  // Sort pages within each group
  for (const g of groups.values()) {
    g.pages.sort((a, b) => {
      // Pages with rerank scores: sort by rerank score descending (magnitude matters)
      const aRerank = a.chunk?.rerank_score;
      const bRerank = b.chunk?.rerank_score;
      if (aRerank != null && bRerank != null) return bRerank - aRerank;
      if (aRerank != null) return -1;
      if (bRerank != null) return 1;
      // Pages with chunks but no rerank: sort by chunk cosine
      if (a.chunk && b.chunk) return b.chunk.score - a.chunk.score;
      if (a.chunk) return -1;
      if (b.chunk) return 1;
      // Summary-only pages: rank by score
      return b.bestScore - a.bestScore;
    });
  }

  // Sort document groups
  if (config.mode === "rrf") {
    return Array.from(groups.values()).sort((a, b) => b.fusionScore - a.fusionScore);
  }

  // Legacy: hard tiering (chunk docs above summary-only docs)
  return Array.from(groups.values()).sort((a, b) => {
    if (a.bestChunkPosition !== null && b.bestChunkPosition !== null) {
      return a.bestChunkPosition - b.bestChunkPosition;
    }
    if (a.bestChunkPosition !== null) return -1;
    if (b.bestChunkPosition !== null) return 1;
    return b.bestScore - a.bestScore;
  });
}

// ---------------------------------------------------------------------------
// Page row within a document group
// ---------------------------------------------------------------------------

function PageHitRow({
  page,
  artifactId,
  workspace,
  query,
  rank,
  devMode,
}: {
  page: PageGroup;
  artifactId: string;
  query: string;
  workspace: string;
  rank: number;
  devMode: boolean;
}) {
  const pageHref = page.pageId
    ? `/${workspace}/documents/${artifactId}/pages/${page.pageId}`
    : `/${workspace}/documents/${artifactId}`;

  const rankClass =
    rank === 0
      ? "border-l-[3px] border-l-accent-text bg-accent-text/[0.04]"
      : "";

  return (
    <div className={`flex items-start gap-3 rounded-lg border border-border-default bg-surface-primary p-3 ${rankClass}`}>
      <div className="relative hidden shrink-0 sm:block">
        <AuthThumbnail
          src={`${API_URL}/artifacts/${artifactId}/pages/${page.pageIndex}/image?size=thumb`}
          href={pageHref}
        />
        <span className="absolute -left-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-text-secondary bg-surface-elevated text-[10px] font-bold text-text-secondary">
          {rank + 1}
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <Link
            href={pageHref}
            className="text-sm font-medium text-accent-text hover:underline"
          >
            {page.pageName ?? `Page ${page.pageIndex + 1}`}
          </Link>
          <ScoreBadge score={page.bestScore} />
        </div>

        {/* Overview (summary match) */}
        {page.summary?.summary_text && (
          <p className="mt-1.5 text-sm italic leading-relaxed text-text-secondary line-clamp-2">
            {highlightMatches(page.summary.summary_text, query)}
          </p>
        )}

        {/* Passage (chunk match) */}
        {page.chunk?.text_preview && (
          <p className="mt-1.5 text-sm leading-relaxed text-text-secondary line-clamp-3">
            {highlightMatches(page.chunk.text_preview, query)}
          </p>
        )}

        {/* Rerank scores — gated by Developer Mode */}
        {devMode && page.chunk?.rerank_score != null && (() => {
          const displacement =
            page.chunk.original_rank != null && page.chunkRerankPosition != null
              ? page.chunk.original_rank - page.chunkRerankPosition
              : null;
          return (
            <div className="mt-1.5 flex items-center gap-2 text-xs text-text-muted">
              <span>vector: {page.chunk.score.toFixed(3)}</span>
              <span>→ rerank: {page.chunk.rerank_score.toFixed(3)}</span>
              {displacement != null && (
                <span
                  className={
                    displacement > 0
                      ? "text-green-600 dark:text-green-400"
                      : displacement < 0
                        ? "text-red-500 dark:text-red-400"
                        : "text-text-muted"
                  }
                >
                  {displacement > 0
                    ? `↑${displacement}`
                    : displacement < 0
                      ? `↓${Math.abs(displacement)}`
                      : "—"}
                </span>
              )}
            </div>
          );
        })()}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Document group card
// ---------------------------------------------------------------------------

function DocumentGroupCard({
  group,
  workspace,
  query,
  rank,
  nextScore,
  devMode,
}: {
  group: DocumentGroup;
  workspace: string;
  query: string;
  rank: number;
  nextScore: number | null;
  devMode: boolean;
}) {
  const [expanded, setExpanded] = useState(true);

  const metaLine = [
    group.authors.length > 0 ? group.authors.join(", ") : null,
    group.presentationDate
      ? new Date(group.presentationDate).getFullYear()
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="rounded-xl border border-border-default bg-surface-elevated p-4">
      {/* Header — always visible */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Link
              href={`/${workspace}/documents/${group.artifactId}`}
              className="text-sm font-semibold text-accent-text hover:underline"
            >
              {group.artifactTitle || "Untitled Document"}
            </Link>
            <ScoreBadge score={group.bestScore} />
            {!expanded && group.pages.length > 0 && (
              <span className="rounded-full bg-surface-hover px-2 py-0.5 text-[11px] font-mono tabular-nums text-text-muted">
                {group.pages.length} {group.pages.length === 1 ? "page" : "pages"}
              </span>
            )}
          </div>
          {metaLine && (
            <p className="mt-0.5 text-xs text-text-muted">{metaLine}</p>
          )}
          {/* Collapsed: show best matching context to jog memory */}
          {!expanded && (() => {
            const topPage = group.pages[0];
            const snippets: string[] = [];
            if (group.artifactSummary?.summary_text)
              snippets.push(group.artifactSummary.summary_text);
            if (topPage?.summary?.summary_text)
              snippets.push(topPage.summary.summary_text);
            if (topPage?.chunk?.text_preview)
              snippets.push(topPage.chunk.text_preview);
            const preview = snippets[0];
            return preview ? (
              <p className="mt-1 text-xs leading-relaxed text-text-secondary line-clamp-2">
                {highlightMatches(preview, query)}
              </p>
            ) : null;
          })()}
        </div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-0.5 shrink-0 rounded-md p-1 text-text-muted transition-colors hover:bg-surface-hover hover:text-text-secondary"
          aria-label={expanded ? "Collapse" : "Expand"}
        >
          <ChevronDown
            className={`h-4 w-4 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
          />
        </button>
      </div>

      {/* Expanded content */}
      {expanded && (
        <>
          {/* RRF scoring debug — gated by Developer Mode in Settings */}
          {devMode && (() => {
            const { k, chunkWeight, summaryWeight } = SCORING_CONFIG;
            const chunkRRF = group.bestChunkPosition !== null
              ? chunkWeight / (k + group.bestChunkPosition)
              : 0;
            const summaryRRF = group.bestSummaryRank !== null
              ? summaryWeight / (k + group.bestSummaryRank)
              : 0;
            const gap = nextScore !== null ? group.fusionScore - nextScore : null;

            return (
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 rounded bg-surface-primary px-2 py-1 text-[10px] font-mono text-text-muted">
                <span className="font-semibold text-text-secondary">
                  #{rank + 1}
                </span>
                <span>
                  fusion: {group.fusionScore.toFixed(5)}
                </span>
                {group.bestChunkPosition !== null && (
                  <span className="text-blue-500">
                    chunk#{group.bestChunkPosition} → {chunkRRF.toFixed(5)}
                  </span>
                )}
                {group.bestSummaryRank !== null && (
                  <span className="text-purple-500">
                    summary#{group.bestSummaryRank} → {summaryRRF.toFixed(5)}
                  </span>
                )}
                {group.bestChunkPosition !== null && group.bestSummaryRank !== null && (
                  <span className="text-green-500">multi-hit</span>
                )}
                {group.bestChunkPosition === null && (
                  <span className="text-orange-400">summary-only</span>
                )}
                {group.bestSummaryRank === null && (
                  <span className="text-orange-400">chunk-only</span>
                )}
                {gap !== null && (
                  <span className="text-text-muted">
                    gap to #{rank + 2}: +{gap.toFixed(5)}
                  </span>
                )}
              </div>
            );
          })()}

          {/* Artifact-level summary */}
          {group.artifactSummary?.summary_text && (
            <p className="mt-2 text-sm leading-relaxed text-text-secondary line-clamp-3">
              {highlightMatches(group.artifactSummary.summary_text, query)}
            </p>
          )}

          {/* Page rows */}
          {group.pages.length > 0 && (
            <div className="mt-3 space-y-2">
              {group.pages.map((p, i) => (
                <PageHitRow
                  key={p.pageId ?? `page-${p.pageIndex}-${i}`}
                  page={p}
                  artifactId={group.artifactId}
                  workspace={workspace}
                  query={query}
                  rank={i}
                  devMode={devMode}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function HierarchicalSearchResults({
  data,
  workspace,
}: HierarchicalSearchResultsProps) {
  const devMode = useDevModeStore((s) => s.enabled);
  const groups = useMemo(
    () => buildDocumentGroups(data.summary_hits, data.chunk_hits),
    [data.summary_hits, data.chunk_hits],
  );

  const totalPages = groups.reduce((sum, g) => sum + g.pages.length, 0);

  return (
    <div className="mt-6">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-text-secondary">
          {groups.length} document{groups.length !== 1 ? "s" : ""},{" "}
          {totalPages} page{totalPages !== 1 ? "s" : ""} for{" "}
          <span className="font-medium text-text-primary">
            &ldquo;{data.query}&rdquo;
          </span>
        </p>
        <span className="text-xs text-text-muted">
          Model: {data.model_used}
        </span>
      </div>

      {devMode && data.chunk_rerank_info && void console.log("[rerank:hierarchical]", data.chunk_rerank_info)}
      {devMode && void console.log("[scoring]", { mode: SCORING_CONFIG.mode, k: SCORING_CONFIG.k, chunkWeight: SCORING_CONFIG.chunkWeight, summaryWeight: SCORING_CONFIG.summaryWeight })}

      <div className="space-y-4">
        {groups.map((g, i) => (
          <DocumentGroupCard
            key={g.artifactId}
            group={g}
            workspace={workspace}
            query={data.query}
            rank={i}
            nextScore={i < groups.length - 1 ? groups[i + 1].fusionScore : null}
            devMode={devMode}
          />
        ))}
      </div>
    </div>
  );
}
