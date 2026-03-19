"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Button } from "primereact/button";
import { Column } from "primereact/column";
import { DataTable } from "primereact/datatable";
import { Message } from "primereact/message";
import { Tag } from "primereact/tag";
import { FileText } from "lucide-react";

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
    return <Tag value={label} severity="info" rounded />;
  };

  const pagesTemplate = (row: ArtifactResponse) => (
    <span className="text-text-secondary">{row.pages?.length ?? 0}</span>
  );

  const authorsTemplate = (row: ArtifactResponse) => {
    const authors = row.author_mentions;
    if (!authors?.length) return <span className="text-text-muted">—</span>;
    return (
      <span className="text-sm text-text-secondary">
        {authors.map((a) => a.name).join(", ")}
      </span>
    );
  };

  const dateTemplate = (row: ArtifactResponse) => {
    const pd = row.presentation_date;
    if (!pd) return <span className="text-text-muted">—</span>;
    return (
      <span className="text-sm text-text-secondary">
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
        {tms.slice(0, 3).map((tm, i) => (
          <Tag key={`${tm.tag}-${i}`} value={tm.tag} severity="secondary" rounded />
        ))}
        {tms.length > 3 && (
          <span className="text-xs text-text-muted">+{tms.length - 3}</span>
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
          <Link href={`/${workspace}/documents/upload`}>
            <Button label="Upload" icon="pi pi-upload" />
          </Link>
        }
      />

      {error && (
        <div className="mb-4">
          <Message
            severity="error"
            text="Failed to load documents. Is the backend running?"
          />
        </div>
      )}

      {isEmpty ? (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Upload your first document to start extracting insights."
          action={
            <Link href={`/${workspace}/documents/upload`}>
              <Button label="Upload Document" icon="pi pi-upload" />
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
          <Column header="Tags" body={tagsTemplate} style={{ width: "200px" }} />
        </DataTable>
      )}
    </div>
  );
}
