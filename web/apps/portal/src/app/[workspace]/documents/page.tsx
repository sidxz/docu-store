"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Column } from "primereact/column";
import { DataTable } from "primereact/datatable";
import { FileText, Upload } from "lucide-react";

import type { components } from "@docu-store/api-client";
import { useArtifacts } from "@/hooks/use-artifacts";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";

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
        className="font-medium text-accent-text hover:underline"
      >
        {title}
      </Link>
    );
  };

  const typeTemplate = (row: ArtifactResponse) => {
    const label =
      ARTIFACT_TYPE_LABELS[row.artifact_type] ?? row.artifact_type;
    return (
      <span className="inline-flex rounded-md bg-accent-light px-2 py-0.5 text-xs font-medium text-accent-text">
        {label}
      </span>
    );
  };

  const pagesTemplate = (row: ArtifactResponse) => (
    <span className="text-text-secondary">{row.pages?.length ?? 0}</span>
  );

  const tagsTemplate = (row: ArtifactResponse) => {
    const tags = row.tags;
    if (!tags?.length) return <span className="text-text-muted">—</span>;
    return (
      <div className="flex flex-wrap gap-1">
        {tags.slice(0, 3).map((tag) => (
          <span
            key={tag}
            className="rounded bg-border-subtle px-1.5 py-0.5 text-xs text-text-secondary"
          >
            {tag}
          </span>
        ))}
        {tags.length > 3 && (
          <span className="text-xs text-text-muted">+{tags.length - 3}</span>
        )}
      </div>
    );
  };

  const isEmpty = !isLoading && (!artifacts || artifacts.length === 0) && !error;

  return (
    <div>
      <PageHeader
        icon={FileText}
        title="Documents"
        subtitle="Manage your uploaded documents"
        actions={
          <Link
            href={`/${workspace}/documents/upload`}
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
          >
            <Upload className="h-4 w-4" />
            Upload
          </Link>
        }
      />

      {error && (
        <div className="mb-4 rounded-lg border border-ds-error/20 bg-ds-error/5 p-3 text-sm text-ds-error">
          Failed to load documents. Is the backend running?
        </div>
      )}

      {isEmpty ? (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Upload your first document to start extracting insights."
          action={
            <Link
              href={`/${workspace}/documents/upload`}
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
            >
              <Upload className="h-4 w-4" />
              Upload Document
            </Link>
          }
        />
      ) : (
        <DataTable
          value={artifacts ?? []}
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
            header="Pages"
            body={pagesTemplate}
            style={{ width: "80px" }}
          />
          <Column header="Tags" body={tagsTemplate} style={{ width: "200px" }} />
        </DataTable>
      )}
    </div>
  );
}
