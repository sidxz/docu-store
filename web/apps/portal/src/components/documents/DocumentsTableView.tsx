import Link from "next/link";
import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import type { ArtifactResponse } from "@docu-store/types";
import { ARTIFACT_TYPE_LABELS } from "@/lib/constants";
import { AuthThumbnail } from "@/components/ui/TableThumbnail";
import { DataTable } from "@/components/ui/data-table";
import { Badge } from "@/components/ui/badge";

type ArtifactWithSearch = ArtifactResponse & { _search: string };

const typeOptions = Object.entries(ARTIFACT_TYPE_LABELS).map(([value, label]) => ({
  label,
  value,
}));

interface DocumentsTableViewProps {
  artifacts: ArtifactResponse[];
  workspace: string;
  isLoading: boolean;
}

export function DocumentsTableView({
  artifacts,
  workspace,
  isLoading,
}: DocumentsTableViewProps) {
  const enriched = useMemo<ArtifactWithSearch[]>(
    () =>
      artifacts.map((a) => ({
        ...a,
        _search: [
          a.title_mention?.title,
          a.source_filename,
          ...(a.author_mentions?.map((am: { name: string }) => am.name) ?? []),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase(),
      })),
    [artifacts],
  );

  /* ── Composite "Document" column: thumbnail + title + authors ─────── */
  const documentTemplate = (row: ArtifactResponse) => {
    const title = row.title_mention?.title ?? row.source_filename ?? "Untitled";
    const href = `/${workspace}/documents/${row.artifact_id}`;
    const authors = row.author_mentions;
    return (
      <div className="flex items-center gap-3">
        <AuthThumbnail artifactId={row.artifact_id} href={href} size="md" />
        <div className="min-w-0">
          <Link
            href={href}
            className="text-sm font-medium text-accent-text hover:underline line-clamp-2"
          >
            {title}
          </Link>
          {authors?.length > 0 && (
            <p className="mt-0.5 text-xs text-text-muted line-clamp-1">
              {authors.map((a: { name: string }) => a.name).join(", ")}
            </p>
          )}
        </div>
      </div>
    );
  };

  const typeTemplate = (row: ArtifactResponse) => {
    const label = ARTIFACT_TYPE_LABELS[row.artifact_type] ?? row.artifact_type;
    return (
      <Badge variant="info" className="rounded-full">
        {label}
      </Badge>
    );
  };

  const dateTemplate = (row: ArtifactResponse) => {
    const pd = row.presentation_date;
    if (!pd) return <span className="text-xs text-text-muted">—</span>;
    return (
      <span className="text-xs tabular-nums text-text-secondary">
        {new Date(pd.date).toLocaleDateString(undefined, {
          year: "numeric",
          month: "short",
          day: "numeric",
        })}
      </span>
    );
  };

  const pagesTemplate = (row: ArtifactResponse) => (
    <span className="text-xs tabular-nums text-text-secondary">
      {row.pages?.length ?? 0}
    </span>
  );

  const tagsTemplate = (row: ArtifactResponse) => {
    const tms = row.tag_mentions;
    if (!tms?.length) return <span className="text-xs text-text-muted">—</span>;
    return (
      <div className="flex flex-wrap gap-1">
        {tms.slice(0, 3).map(
          (tm: { tag: string; page_count?: number | null }, i: number) => (
            <span
              key={`${tm.tag}-${i}`}
              className="inline-flex items-center rounded-full bg-surface-hover px-2 py-0.5 text-[11px] text-text-secondary"
            >
              {tm.tag}
              {tm.page_count ? ` (${tm.page_count})` : ""}
            </span>
          ),
        )}
        {tms.length > 3 && (
          <span className="text-[11px] text-text-muted">+{tms.length - 3}</span>
        )}
      </div>
    );
  };

  const columns: ColumnDef<ArtifactWithSearch, unknown>[] = [
    {
      id: "document",
      header: "Document",
      accessorKey: "_search",
      filterFn: "includesString",
      sortingFn: (a, b) =>
        (a.original.source_filename ?? "").localeCompare(b.original.source_filename ?? ""),
      meta: { filter: { variant: "text", placeholder: "Search…" } },
      cell: ({ row }) => documentTemplate(row.original),
    },
    {
      id: "artifact_type",
      header: "Type",
      accessorKey: "artifact_type",
      filterFn: "equalsString",
      size: 160,
      meta: { filter: { variant: "select", options: typeOptions } },
      cell: ({ row }) => typeTemplate(row.original),
    },
    {
      id: "date",
      header: "Date",
      accessorFn: (r) => r.presentation_date?.date ?? "",
      size: 110,
      cell: ({ row }) => dateTemplate(row.original),
    },
    {
      id: "pages",
      header: "Pages",
      accessorFn: (r) => r.pages?.length ?? 0,
      size: 70,
      cell: ({ row }) => pagesTemplate(row.original),
    },
    {
      id: "tags",
      header: "Tags",
      enableSorting: false,
      size: 180,
      cell: ({ row }) => tagsTemplate(row.original),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={enriched}
      isLoading={isLoading}
      emptyMessage="No documents found."
      defaultSorting={[{ id: "document", desc: false }]}
    />
  );
}
