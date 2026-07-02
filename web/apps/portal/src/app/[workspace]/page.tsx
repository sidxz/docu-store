"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import {
  FileText,
  BookOpen,
  Atom,
  Activity,
  ArrowRight,
  Upload,
  Search,
  ArrowUpRight,
  X,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/StatCard";
import { LinkButton } from "@/components/ui/LinkButton";
import { useDashboard } from "@/hooks/use-dashboard";
import {
  useRecentSearches,
  useRecentDocuments,
  useDeleteSearchEntry,
  useClearSearchHistory,
} from "@/hooks/use-activity";
import { useSession } from "@/lib/auth";
import { ARTIFACT_TYPE_LABELS } from "@/lib/constants";
import { useAnalytics } from "@/hooks/use-analytics";
import { severityToVariant } from "@/lib/severity";

export default function DashboardPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const { trackEvent } = useAnalytics();
  const { stats, recentArtifacts, isLoading } = useDashboard();
  const { data: recentSearches } = useRecentSearches(5);
  const { data: recentDocs } = useRecentDocuments(5);
  const deleteSearch = useDeleteSearchEntry();
  const clearSearches = useClearSearchHistory();
  const { user } = useSession();

  const firstName = user.name?.split(" ")[0] || "there";

  return (
    <div>
      {/* Greeting */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-text-primary">
          Welcome back, {firstName}
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          Here&apos;s what&apos;s happening in your workspace.
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={FileText}
          label="Documents"
          value={stats.totalArtifacts}
          loading={isLoading}
        />
        <StatCard
          icon={BookOpen}
          label="Pages"
          value={stats.totalPages}
          loading={isLoading}
        />
        <StatCard
          icon={Atom}
          label="Compounds"
          value={stats.totalCompounds}
          loading={isLoading}
        />
        <StatCard
          icon={Activity}
          label="Summarized"
          value={stats.withSummary}
          loading={isLoading}
        />
      </div>

      {/* Two-column layout */}
      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Recent Documents — 2/3 width */}
        <div className="lg:col-span-2 rounded-xl border border-border-default bg-surface-elevated">
          <div className="flex items-center justify-between px-5 py-4">
            <h2 className="text-sm font-semibold text-text-primary">
              Recent Documents
            </h2>
            <Link
              href={`/${workspace}/documents`}
              className="flex items-center gap-1 text-xs font-medium text-accent-text transition-colors hover:text-accent-hover"
            >
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>

          <div className="border-t border-border-default">
            {isLoading ? (
              <div className="divide-y divide-border-subtle">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-4 px-5 py-3.5">
                    <Skeleton className="size-8 rounded-lg" />
                    <div className="flex-1 space-y-1.5">
                      <Skeleton className="h-3.5 w-[60%]" />
                      <Skeleton className="h-3 w-[30%]" />
                    </div>
                  </div>
                ))}
              </div>
            ) : recentArtifacts.length === 0 ? (
              <div className="flex flex-col items-center py-12 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent-light mb-3">
                  <FileText className="h-6 w-6 text-accent-text" />
                </div>
                <p className="text-sm font-medium text-text-primary">
                  No documents yet
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  Upload your first document to get started.
                </p>
                <LinkButton
                  href={`/${workspace}/documents/upload`}
                  label="Upload"
                  icon={Upload}
                  className="mt-4"
                />
              </div>
            ) : (
              <div className="divide-y divide-border-subtle">
                {recentArtifacts.map((artifact) => {
                  const title =
                    artifact.title_mention?.title ||
                    artifact.source_filename ||
                    artifact.artifact_id.slice(0, 8);
                  const typeLabel =
                    ARTIFACT_TYPE_LABELS[artifact.artifact_type] ??
                    artifact.artifact_type;
                  const pageCount = Array.isArray(artifact.pages)
                    ? artifact.pages.length
                    : 0;

                  return (
                    <Link
                      key={artifact.artifact_id}
                      href={`/${workspace}/documents/${artifact.artifact_id}`}
                      className="group flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-surface-sunken"
                    >
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-light transition-colors group-hover:bg-accent-muted">
                        <FileText className="h-4 w-4 text-accent-text" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-text-primary">
                          {title}
                        </p>
                        <div className="mt-0.5 flex items-center gap-2">
                          <Badge variant={severityToVariant.secondary}>
                            {typeLabel}
                          </Badge>
                          {artifact.author_mentions?.length > 0 && (
                            <span className="truncate text-xs text-text-muted">
                              {artifact.author_mentions.map((a) => a.name).join(", ")}
                            </span>
                          )}
                          {artifact.presentation_date && (
                            <span className="shrink-0 text-xs text-text-muted">
                              {new Date(artifact.presentation_date.date).toLocaleDateString(undefined, {
                                year: "numeric",
                                month: "short",
                              })}
                            </span>
                          )}
                          {pageCount > 0 && (
                            <span className="text-xs text-text-muted">
                              {pageCount} {pageCount === 1 ? "page" : "pages"}
                            </span>
                          )}
                        </div>
                      </div>
                      <ArrowUpRight className="h-4 w-4 shrink-0 text-text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right column — Quick Actions + Activity */}
        <div className="space-y-6">
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-text-primary">
              Quick Actions
            </h2>
            <div className="space-y-3">
              <Link
                href={`/${workspace}/documents/upload`}
                onClick={() => trackEvent("dashboard_action", { action: "upload" })}
                className="group flex items-center gap-4 rounded-xl border border-border-default bg-surface-elevated p-4 transition-all hover:shadow-ds hover:border-primary/30"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent-light">
                  <Upload className="h-5 w-5 text-accent-text" />
                </div>
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    Upload Document
                  </p>
                  <p className="text-xs text-text-muted">
                    PDF, PPTX, DOC, DOCX
                  </p>
                </div>
              </Link>

              <Link
                href={`/${workspace}/search`}
                onClick={() => trackEvent("dashboard_action", { action: "search" })}
                className="group flex items-center gap-4 rounded-xl border border-border-default bg-surface-elevated p-4 transition-all hover:shadow-ds hover:border-primary/30"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-feature-search/10">
                  <Search className="h-5 w-5 text-feature-search" />
                </div>
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    Search Documents
                  </p>
                  <p className="text-xs text-text-muted">
                    Semantic search across all content
                  </p>
                </div>
              </Link>

              <Link
                href={`/${workspace}/compounds`}
                onClick={() => trackEvent("dashboard_action", { action: "compounds" })}
                className="group flex items-center gap-4 rounded-xl border border-border-default bg-surface-elevated p-4 transition-all hover:shadow-ds hover:border-primary/30"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-feature-compounds/10">
                  <Atom className="h-5 w-5 text-feature-compounds" />
                </div>
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    Browse Compounds
                  </p>
                  <p className="text-xs text-text-muted">
                    SMILES similarity search
                  </p>
                </div>
              </Link>
            </div>
          </div>

          {/* Recent Searches */}
          {recentSearches && recentSearches.length > 0 && (
            <div className="rounded-xl border border-border-default bg-surface-elevated">
              <div className="flex items-center justify-between px-5 py-3">
                <h2 className="text-sm font-semibold text-text-primary">
                  Recent Searches
                </h2>
                <button
                  onClick={() => clearSearches.mutate()}
                  className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-text-muted transition-colors hover:bg-ds-error/10 hover:text-ds-error"
                >
                  <Trash2 className="h-3 w-3" />
                  Clear
                </button>
              </div>
              <div className="border-t border-border-default divide-y divide-border-subtle">
                {recentSearches.map((entry, i) => (
                  <div
                    key={`${entry.query_text}-${i}`}
                    className="group flex items-center gap-3 px-5 py-2.5 transition-colors hover:bg-surface-sunken"
                  >
                    <Search className="h-3.5 w-3.5 shrink-0 text-text-muted" />
                    <Link
                      href={`/${workspace}/search?q=${encodeURIComponent(entry.query_text)}&mode=${entry.search_mode}`}
                      className="min-w-0 flex-1 truncate text-sm text-text-primary"
                    >
                      {entry.query_text}
                    </Link>
                    <span className="shrink-0 text-xs text-text-muted">
                      {entry.search_mode === "hierarchical" ? "deep" : entry.search_mode}
                    </span>
                    <button
                      onClick={() => deleteSearch.mutate(entry.query_text)}
                      className="shrink-0 rounded p-0.5 text-text-muted opacity-0 transition-all hover:bg-ds-error/10 hover:text-ds-error group-hover:opacity-100"
                      aria-label={`Remove "${entry.query_text}"`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recently Viewed Documents */}
          {recentDocs && recentDocs.length > 0 && (
            <div className="rounded-xl border border-border-default bg-surface-elevated">
              <div className="px-5 py-3">
                <h2 className="text-sm font-semibold text-text-primary">
                  Recently Viewed
                </h2>
              </div>
              <div className="border-t border-border-default divide-y divide-border-subtle">
                {recentDocs.map((entry) => (
                  <Link
                    key={entry.artifact_id}
                    href={`/${workspace}/documents/${entry.artifact_id}`}
                    className="flex items-center gap-3 px-5 py-2.5 transition-colors hover:bg-surface-sunken"
                  >
                    <FileText className="h-3.5 w-3.5 shrink-0 text-text-muted" />
                    <span className="truncate text-sm text-text-primary">
                      {entry.artifact_title ?? entry.artifact_id.slice(0, 12)}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
