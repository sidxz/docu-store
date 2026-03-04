"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Button } from "primereact/button";
import { Column } from "primereact/column";
import { DataTable } from "primereact/datatable";
import { Tag } from "primereact/tag";

import type { components } from "@docu-store/api-client";
import { useArtifacts } from "@/hooks/use-artifacts";

type ArtifactResponse = components["schemas"]["ArtifactResponse"];

const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  GENERIC_PRESENTATION: "Presentation",
  SCIENTIFIC_PRESENTATION: "Scientific Presentation",
  RESEARCH_ARTICLE: "Research Article",
  SCIENTIFIC_DOCUMENT: "Scientific Document",
  DISCLOSURE_DOCUMENT: "Disclosure",
  MINUTE_OF_MEETING: "Minutes",
  UNCLASSIFIED: "Unclassified",
};

export default function DocumentsPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const { data: artifacts, isLoading, error } = useArtifacts();

  const titleTemplate = (row: ArtifactResponse) => {
    const title =
      row.title_mention?.title ?? row.source_filename ?? "Untitled";
    return (
      <Link
        href={`/${workspace}/documents/${row.artifact_id}`}
        className="text-blue-600 hover:underline font-medium"
      >
        {title}
      </Link>
    );
  };

  const typeTemplate = (row: ArtifactResponse) => {
    const label =
      ARTIFACT_TYPE_LABELS[row.artifact_type] ?? row.artifact_type;
    return <Tag value={label} severity="info" />;
  };

  const pagesTemplate = (row: ArtifactResponse) => {
    return <span>{row.pages?.length ?? 0}</span>;
  };

  const tagsTemplate = (row: ArtifactResponse) => {
    const tags = row.tags;
    if (!tags?.length) return <span className="text-gray-400">—</span>;
    return (
      <div className="flex flex-wrap gap-1">
        {tags.slice(0, 3).map((tag) => (
          <Tag key={tag} value={tag} severity="secondary" />
        ))}
        {tags.length > 3 && (
          <span className="text-xs text-gray-400">+{tags.length - 3}</span>
        )}
      </div>
    );
  };

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Documents</h1>
        <Link href={`/${workspace}/documents/upload`}>
          <Button label="Upload" icon="pi pi-upload" size="small" />
        </Link>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          Failed to load documents. Is the backend running?
        </div>
      )}

      <DataTable
        value={artifacts ?? []}
        loading={isLoading}
        paginator
        rows={20}
        rowsPerPageOptions={[10, 20, 50]}
        emptyMessage="No documents found."
        stripedRows
        sortField="source_filename"
        sortOrder={1}
        className="rounded-lg border border-gray-200"
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
          header="Pages"
          body={pagesTemplate}
          style={{ width: "80px" }}
        />
        <Column header="Tags" body={tagsTemplate} style={{ width: "200px" }} />
      </DataTable>
    </div>
  );
}
