"use client";

import Link from "next/link";
import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import type { components } from "@docu-store/api-client";
import { API_URL } from "@/lib/constants";
import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { DataTable } from "@/components/ui/data-table";

type PageResponse = components["schemas"]["PageResponse"];

interface PagesTabProps {
  pages: PageResponse[] | string[];
  workspace: string;
  artifactId: string;
}

type PageWithSearch = PageResponse & { _search: string };

/* ── Small inline thumbnail for page rows ─────────────────────────── */
function PageThumbnail({ artifactId, pageIndex, href }: {
  artifactId: string;
  pageIndex: number;
  href: string;
}) {
  const src = `${API_URL}/artifacts/${artifactId}/pages/${pageIndex}/image?size=thumb`;
  const { blobUrl, error } = useAuthBlobUrl(src);

  if (error) return null;

  return (
    <Link href={href} className="block h-20 w-20 shrink-0">
      {blobUrl && (
        <img
          src={blobUrl}
          alt=""
          className="h-20 w-20 rounded-md border border-border-subtle object-cover object-top"
        />
      )}
    </Link>
  );
}

export function PagesTab({ pages, workspace, artifactId }: PagesTabProps) {
  const isPageObjects = pages.length > 0 && typeof pages[0] === "object";

  /* ── Rich page table (full PageResponse objects) ─────────────────── */
  if (isPageObjects) {
    const pageData = pages as PageResponse[];

    const enriched = useMemo<PageWithSearch[]>(
      () =>
        pageData.map((p) => ({
          ...p,
          _search: [
            p.name,
            `page ${p.index}`,
            p.summary_candidate?.summary,
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase(),
        })),
      [pageData],
    );

    const pageTemplate = (row: PageResponse) => {
      const href = `/${workspace}/documents/${artifactId}/pages/${row.page_id}`;
      return (
        <div className="flex items-center gap-3">
          <PageThumbnail
            artifactId={artifactId}
            pageIndex={row.index}
            href={href}
          />
          <div className="min-w-0">
            <Link
              href={href}
              className="text-sm font-medium text-accent-text hover:underline"
            >
              {row.name ?? `Page ${row.index + 1}`}
            </Link>
            {row.summary_candidate?.summary && (
              <p className="mt-0.5 text-xs leading-relaxed text-text-muted line-clamp-3">
                {row.summary_candidate.summary}
              </p>
            )}
          </div>
        </div>
      );
    };

    const compoundsTemplate = (row: PageResponse) => {
      const count = row.compound_mentions?.length ?? 0;
      if (!count) return <span className="text-xs text-text-muted">—</span>;
      return (
        <span className="inline-flex items-center rounded-full bg-surface-hover px-2 py-0.5 text-[11px] font-mono tabular-nums text-text-secondary">
          {count}
        </span>
      );
    };

    const columns: ColumnDef<PageWithSearch, unknown>[] = [
      {
        id: "page",
        header: "Page",
        accessorKey: "_search",
        filterFn: "includesString",
        sortingFn: (a, b) => a.original.index - b.original.index,
        meta: { filter: { variant: "text", placeholder: "Search pages…" } },
        cell: ({ row }) => pageTemplate(row.original),
      },
      {
        id: "index",
        header: "#",
        accessorKey: "index",
        size: 60,
        cell: ({ row }) => (
          <span className="font-mono text-xs tabular-nums text-text-secondary">{row.original.index + 1}</span>
        ),
      },
      {
        id: "compounds",
        header: "Compounds",
        accessorFn: (r) => r.compound_mentions?.length ?? 0,
        size: 100,
        cell: ({ row }) => compoundsTemplate(row.original),
      },
    ];

    return (
      <DataTable
        columns={columns}
        data={enriched}
        emptyMessage="No pages."
        defaultSorting={[{ id: "page", desc: false }]}
      />
    );
  }

  /* ── Fallback: string page IDs only ──────────────────────────────── */
  const fallbackData = (pages as string[]).map((pageId, idx) => ({
    page_id: pageId,
    index: idx,
  }));

  const fallbackColumns: ColumnDef<{ page_id: string; index: number }, unknown>[] = [
    {
      id: "page",
      header: "Page",
      enableSorting: false,
      cell: ({ row }) => (
        <Link
          href={`/${workspace}/documents/${artifactId}/pages/${row.original.page_id}`}
          className="text-sm font-medium text-accent-text hover:underline"
        >
          Page {row.original.index + 1}
        </Link>
      ),
    },
    {
      id: "index",
      header: "#",
      accessorKey: "index",
      enableSorting: false,
      size: 60,
      cell: ({ row }) => (
        <span className="font-mono text-xs tabular-nums text-text-secondary">{row.original.index + 1}</span>
      ),
    },
  ];

  return (
    <DataTable columns={fallbackColumns} data={fallbackData} emptyMessage="No pages." />
  );
}
