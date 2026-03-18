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
} from "lucide-react";
import { Skeleton } from "primereact/skeleton";
import { Tag } from "primereact/tag";

import { StatCard } from "@/components/ui/StatCard";
import { useDashboard } from "@/hooks/use-dashboard";
import { useSession } from "@/lib/auth";

const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  GENERIC_PRESENTATION: "Presentation",
  SCIENTIFIC_PRESENTATION: "Sci. Presentation",
  RESEARCH_ARTICLE: "Article",
  SCIENTIFIC_DOCUMENT: "Sci. Document",
  DISCLOSURE_DOCUMENT: "Disclosure",
  MINUTE_OF_MEETING: "Minutes",
  UNCLASSIFIED: "Unclassified",
};

export default function DashboardPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const { stats, recentArtifacts, isLoading } = useDashboard();
  const { user } = useSession();

  const firstName = user.name?.split(" ")[0] || "there";

  return (
    <div>
      {/* Greeting */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-text-primary">
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
                    <Skeleton width="2rem" height="2rem" borderRadius="0.5rem" />
                    <div className="flex-1 space-y-1.5">
                      <Skeleton width="60%" height="0.875rem" />
                      <Skeleton width="30%" height="0.75rem" />
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
                <Link
                  href={`/${workspace}/documents/upload`}
                  className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
                >
                  <Upload className="h-3.5 w-3.5" />
                  Upload
                </Link>
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
                          <Tag
                            value={typeLabel}
                            severity="secondary"
                            rounded
                            className="!text-xs !py-0"
                          />
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

        {/* Quick Actions — 1/3 width */}
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-text-primary">
            Quick Actions
          </h2>
          <div className="space-y-3">
            <Link
              href={`/${workspace}/documents/upload`}
              className="group flex items-center gap-4 rounded-xl border border-border-default bg-surface-elevated p-4 transition-all hover:shadow-ds hover:border-accent/30"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-500/10">
                <Upload className="h-5 w-5 text-blue-500" />
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
              className="group flex items-center gap-4 rounded-xl border border-border-default bg-surface-elevated p-4 transition-all hover:shadow-ds hover:border-accent/30"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-violet-500/10">
                <Search className="h-5 w-5 text-violet-500" />
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
              className="group flex items-center gap-4 rounded-xl border border-border-default bg-surface-elevated p-4 transition-all hover:shadow-ds hover:border-accent/30"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10">
                <Atom className="h-5 w-5 text-emerald-500" />
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
      </div>
    </div>
  );
}
