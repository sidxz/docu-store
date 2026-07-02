import Link from "next/link";
import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import type { ArtifactBrowseItemDTO } from "@docu-store/types";
import { ARTIFACT_TYPE_LABELS } from "@/lib/constants";
import { AuthThumbnail } from "@/components/ui/TableThumbnail";
import { DataTable } from "@/components/ui/data-table";
import { Badge } from "@/components/ui/badge";

type BrowseItemWithSearch = ArtifactBrowseItemDTO & { _search: string };

interface FolderArtifactListProps {
  artifacts: ArtifactBrowseItemDTO[] | undefined;
  workspace: string;
  isLoading?: boolean;
}

const typeOptions = Object.entries(ARTIFACT_TYPE_LABELS).map(([value, label]) => ({
  label,
  value,
}));

export function FolderArtifactList({
  artifacts,
  workspace,
  isLoading,
}: FolderArtifactListProps) {
  const enriched = useMemo<BrowseItemWithSearch[]>(
    () =>
      (artifacts ?? []).map((a) => ({
        ...a,
        _search: [a.title, a.source_filename, ...(a.author_names ?? [])]
          .filter(Boolean)
          .join(" ")
          .toLowerCase(),
      })),
    [artifacts],
  );

  /* ── Composite "Document" column: thumbnail + title + authors ─────── */
  const documentTemplate = (row: ArtifactBrowseItemDTO) => {
    const title = row.title ?? row.source_filename ?? "Untitled";
    const href = `/${workspace}/documents/${row.artifact_id}`;
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
          {row.author_names?.length > 0 && (
            <p className="mt-0.5 text-xs text-text-muted line-clamp-1">
              {row.author_names.join(", ")}
            </p>
          )}
        </div>
      </div>
    );
  };

  const typeTemplate = (row: ArtifactBrowseItemDTO) => {
    const label = ARTIFACT_TYPE_LABELS[row.artifact_type] ?? row.artifact_type;
    return (
      <Badge variant="info" className="rounded-full">
        {label}
      </Badge>
    );
  };

  const dateTemplate = (row: ArtifactBrowseItemDTO) => {
    if (!row.presentation_date)
      return <span className="text-xs text-text-muted">—</span>;
    return (
      <span className="text-xs tabular-nums text-text-secondary">
        {new Date(row.presentation_date).toLocaleDateString(undefined, {
          year: "numeric",
          month: "short",
          day: "numeric",
        })}
      </span>
    );
  };

  const pagesTemplate = (row: ArtifactBrowseItemDTO) => (
    <span className="text-xs tabular-nums text-text-secondary">{row.page_count}</span>
  );

  const foundOnTemplate = (row: ArtifactBrowseItemDTO) => {
    const sources = row.tag_page_sources;
    if (!sources?.length) return <span className="text-xs text-text-muted">—</span>;

    const sorted = [...sources].sort((a, b) => a.page_index - b.page_index);
    return (
      <div className="flex flex-wrap gap-1">
        {sorted.map((src) => (
          <Link
            key={src.page_id}
            href={`/${workspace}/documents/${row.artifact_id}/pages/${src.page_id}`}
            className="inline-flex items-center rounded-full bg-surface-hover px-2 py-0.5 text-[11px] tabular-nums text-accent-text hover:bg-accent-text/10"
          >
            p.{src.page_index + 1}
          </Link>
        ))}
      </div>
    );
  };

  const columns: ColumnDef<BrowseItemWithSearch, unknown>[] = [
    {
      id: "document",
      header: "Document",
      accessorKey: "_search",
      filterFn: "includesString",
      sortingFn: (a, b) =>
        (a.original.title ?? "").localeCompare(b.original.title ?? ""),
      meta: { filter: { variant: "text", placeholder: "Search..." } },
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
      accessorFn: (r) => r.presentation_date ?? "",
      size: 110,
      cell: ({ row }) => dateTemplate(row.original),
    },
    {
      id: "pages",
      header: "Pages",
      accessorKey: "page_count",
      size: 70,
      cell: ({ row }) => pagesTemplate(row.original),
    },
    {
      id: "found_on",
      header: "Found on",
      enableSorting: false,
      size: 130,
      cell: ({ row }) => foundOnTemplate(row.original),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={enriched}
      isLoading={isLoading}
      emptyMessage="No documents in this folder."
      defaultSorting={[{ id: "document", desc: false }]}
    />
  );
}
