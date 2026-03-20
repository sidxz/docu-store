import Link from "next/link";
import { Column } from "primereact/column";
import { DataTable } from "primereact/datatable";

import type { components } from "@docu-store/api-client";

type PageResponse = components["schemas"]["PageResponse"];

interface PagesTabProps {
  pages: PageResponse[] | string[];
  workspace: string;
  artifactId: string;
}

export function PagesTab({ pages, workspace, artifactId }: PagesTabProps) {
  const isPageObjects = pages.length > 0 && typeof pages[0] === "object";

  if (isPageObjects) {
    return (
      <div className="pt-4">
        <DataTable
          value={pages as PageResponse[]}
          className="rounded-xl border border-border-default"
          emptyMessage="No pages."
          rowHover
        >
          <Column
            header="Name"
            body={(row: PageResponse) => (
              <Link
                href={`/${workspace}/documents/${artifactId}/pages/${row.page_id}`}
                className="font-medium text-accent-text hover:underline"
              >
                {row.name ?? `Page ${row.index}`}
              </Link>
            )}
          />
          <Column
            field="index"
            header="Index"
            style={{ width: "80px" }}
          />
          <Column
            header="Summary"
            body={(row: PageResponse) => {
              const summary = row.summary_candidate?.summary;
              return summary ? (
                <span className="block max-w-md truncate text-sm text-text-secondary">
                  {summary.slice(0, 120)}
                </span>
              ) : (
                <span className="text-text-muted">—</span>
              );
            }}
          />
          <Column
            header="Compounds"
            body={(row: PageResponse) =>
              row.compound_mentions?.length ?? 0
            }
            style={{ width: "100px" }}
          />
        </DataTable>
      </div>
    );
  }

  return (
    <div className="pt-4">
      <DataTable
        value={(pages as string[]).map((pageId, idx) => ({
          page_id: pageId,
          index: idx,
        }))}
        className="rounded-xl border border-border-default"
        emptyMessage="No pages."
        rowHover
      >
        <Column
          header="Page"
          body={(row: { page_id: string; index: number }) => (
            <Link
              href={`/${workspace}/documents/${artifactId}/pages/${row.page_id}`}
              className="font-mono text-sm text-accent-text hover:underline"
            >
              {row.page_id}
            </Link>
          )}
        />
        <Column
          field="index"
          header="Index"
          style={{ width: "80px" }}
        />
      </DataTable>
    </div>
  );
}
