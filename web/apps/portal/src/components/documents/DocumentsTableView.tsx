import Link from "next/link";
import { Column } from "primereact/column";
import { DataTable } from "primereact/datatable";
import { Tag } from "primereact/tag";

import type { ArtifactResponse } from "@docu-store/types";
import { ARTIFACT_TYPE_LABELS } from "@/lib/constants";

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
  const titleTemplate = (row: ArtifactResponse) => {
    const title = row.title_mention?.title ?? row.source_filename ?? "Untitled";
    return (
      <Link
        href={`/${workspace}/documents/${row.artifact_id}`}
        className="font-medium text-accent-text hover:underline"
      >
        {title}
      </Link>
    );
  };

  const typeTemplate = (row: ArtifactResponse) => {
    const label = ARTIFACT_TYPE_LABELS[row.artifact_type] ?? row.artifact_type;
    return <Tag value={label} severity="info" />;
  };

  const pagesTemplate = (row: ArtifactResponse) => (
    <span className="tabular-nums text-text-secondary">
      {row.pages?.length ?? 0}
    </span>
  );

  const authorsTemplate = (row: ArtifactResponse) => {
    const authors = row.author_mentions;
    if (!authors?.length) return <span className="text-text-muted">—</span>;
    return (
      <span className="text-text-secondary">
        {authors.map((a: { name: string }) => a.name).join(", ")}
      </span>
    );
  };

  const dateTemplate = (row: ArtifactResponse) => {
    const pd = row.presentation_date;
    if (!pd) return <span className="text-text-muted">—</span>;
    return (
      <span className="tabular-nums text-text-secondary">
        {new Date(pd.date).toLocaleDateString(undefined, {
          year: "numeric",
          month: "short",
          day: "numeric",
        })}
      </span>
    );
  };

  const tagsTemplate = (row: ArtifactResponse) => {
    const tms = row.tag_mentions;
    if (!tms?.length) return <span className="text-text-muted">—</span>;
    return (
      <div className="flex flex-wrap gap-1">
        {tms
          .slice(0, 3)
          .map(
            (tm: { tag: string; page_count?: number | null }, i: number) => (
              <Tag
                key={`${tm.tag}-${i}`}
                value={
                  tm.page_count ? `${tm.tag} (${tm.page_count})` : tm.tag
                }
                severity="secondary"
              />
            ),
          )}
        {tms.length > 3 && (
          <span className="text-xs text-text-muted">+{tms.length - 3}</span>
        )}
      </div>
    );
  };

  return (
    <DataTable
      value={artifacts}
      loading={isLoading}
      paginator
      rows={20}
      rowsPerPageOptions={[10, 20, 50]}
      emptyMessage="No documents found."
      sortField="source_filename"
      sortOrder={1}
      className="rounded-xl border border-border-default"
      rowHover
    >
      <Column
        header="Title"
        body={titleTemplate}
        sortable
        sortField="source_filename"
      />
      <Column
        header="Type"
        body={typeTemplate}
        sortable
        sortField="artifact_type"
        style={{ width: "180px" }}
      />
      <Column
        header="Authors"
        body={authorsTemplate}
        style={{ width: "200px" }}
      />
      <Column
        header="Date"
        body={dateTemplate}
        sortable
        sortField="presentation_date.date"
        style={{ width: "120px" }}
      />
      <Column
        header="Pages"
        body={pagesTemplate}
        style={{ width: "80px" }}
      />
      <Column
        header="Tags"
        body={tagsTemplate}
        style={{ width: "200px" }}
      />
    </DataTable>
  );
}
