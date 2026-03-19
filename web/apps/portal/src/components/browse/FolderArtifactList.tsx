import Link from "next/link";
import { Column } from "primereact/column";
import { DataTable } from "primereact/datatable";
import { Tag } from "primereact/tag";
import type { ArtifactBrowseItemDTO } from "@docu-store/types";

const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  GENERIC_PRESENTATION: "Presentation",
  SCIENTIFIC_PRESENTATION: "Scientific Presentation",
  RESEARCH_ARTICLE: "Research Article",
  SCIENTIFIC_DOCUMENT: "Scientific Document",
  DISCLOSURE_DOCUMENT: "Disclosure",
  MINUTE_OF_MEETING: "Minutes",
  UNCLASSIFIED: "Unclassified",
};

interface FolderArtifactListProps {
  artifacts: ArtifactBrowseItemDTO[] | undefined;
  workspace: string;
  isLoading?: boolean;
}

export function FolderArtifactList({
  artifacts,
  workspace,
  isLoading,
}: FolderArtifactListProps) {
  const titleTemplate = (row: ArtifactBrowseItemDTO) => {
    const title = row.title ?? row.source_filename ?? "Untitled";
    return (
      <Link
        href={`/${workspace}/documents/${row.artifact_id}`}
        className="font-medium text-accent-text hover:underline"
      >
        {title}
      </Link>
    );
  };

  const typeTemplate = (row: ArtifactBrowseItemDTO) => {
    const label =
      ARTIFACT_TYPE_LABELS[row.artifact_type] ?? row.artifact_type;
    return <Tag value={label} severity="info" rounded />;
  };

  const authorsTemplate = (row: ArtifactBrowseItemDTO) => {
    if (!row.author_names?.length)
      return <span className="text-text-muted">—</span>;
    return (
      <span className="text-sm text-text-secondary">
        {row.author_names.join(", ")}
      </span>
    );
  };

  const dateTemplate = (row: ArtifactBrowseItemDTO) => {
    if (!row.presentation_date)
      return <span className="text-text-muted">—</span>;
    return (
      <span className="text-sm text-text-secondary">
        {new Date(row.presentation_date).toLocaleDateString(undefined, {
          year: "numeric",
          month: "short",
          day: "numeric",
        })}
      </span>
    );
  };

  const pagesTemplate = (row: ArtifactBrowseItemDTO) => (
    <span className="text-text-secondary">{row.page_count}</span>
  );

  return (
    <DataTable
      value={artifacts ?? []}
      loading={isLoading}
      paginator
      rows={20}
      rowsPerPageOptions={[10, 20, 50]}
      emptyMessage="No documents in this folder."
      className="rounded-xl border border-border-default"
      rowHover
    >
      <Column header="Title" body={titleTemplate} />
      <Column
        header="Type"
        body={typeTemplate}
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
        style={{ width: "120px" }}
      />
      <Column
        header="Pages"
        body={pagesTemplate}
        style={{ width: "80px" }}
      />
    </DataTable>
  );
}
