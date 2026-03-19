"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Button } from "primereact/button";
import { Column } from "primereact/column";
import { DataTable } from "primereact/datatable";
import { IconField } from "primereact/iconfield";
import { InputIcon } from "primereact/inputicon";
import { InputText } from "primereact/inputtext";
import { Message } from "primereact/message";
import { SelectButton } from "primereact/selectbutton";
import { Tag } from "primereact/tag";
import { FileText } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import type { components } from "@docu-store/api-client";
import type { TagCategoryDTO, TagFolderDTO } from "@docu-store/types";
import { useArtifacts } from "@/hooks/use-artifacts";
import { useTagCategories, useTagFolders, useFolderArtifacts } from "@/hooks/use-browse";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { CategoryBar } from "@/components/browse/CategoryBar";
import { FolderGrid } from "@/components/browse/FolderGrid";
import { FolderArtifactList } from "@/components/browse/FolderArtifactList";
import { BrowseBreadcrumb } from "@/components/browse/BrowseBreadcrumb";
import { queryKeys } from "@/lib/query-keys";
import { API_URL } from "@/lib/constants";
import { getAuthzClient } from "@/lib/authz-client";

type ArtifactResponse = components["schemas"]["ArtifactResponse"];
type ViewMode = "browse" | "table";

const VIEW_MODES = [
  { label: "Browse", value: "browse" as ViewMode },
  { label: "Table", value: "table" as ViewMode },
];

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
  const queryClient = useQueryClient();

  // View mode
  const [viewMode, setViewMode] = useState<ViewMode>("browse");

  // Browse state
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedCategoryMeta, setSelectedCategoryMeta] = useState<TagCategoryDTO | null>(null);
  const [selectedFolder, setSelectedFolder] = useState<TagFolderDTO | null>(null);
  const [dateParent, setDateParent] = useState<string | undefined>();
  const [folderFilter, setFolderFilter] = useState("");

  // Queries
  const { data: artifacts, isLoading: tableLoading, error: tableError } = useArtifacts();
  const { data: categoriesData, isLoading: categoriesLoading } = useTagCategories();
  const { data: foldersData, isLoading: foldersLoading } = useTagFolders(
    selectedCategory,
    dateParent,
  );
  const { data: folderArtifacts, isLoading: folderArtifactsLoading } = useFolderArtifacts(
    selectedCategory,
    selectedFolder?.tag_value ?? null,
  );

  // Client-side folder filter
  const filteredFolders = useMemo(() => {
    const folders = foldersData?.folders;
    if (!folders || !folderFilter.trim()) return folders;
    const q = folderFilter.trim().toLowerCase();
    return folders.filter((f) => f.display_name.toLowerCase().includes(q));
  }, [foldersData?.folders, folderFilter]);

  // Auto-select first category when categories load
  useEffect(() => {
    if (categoriesData?.categories?.length && !selectedCategory) {
      const first = categoriesData.categories[0];
      setSelectedCategory(first.entity_type);
      setSelectedCategoryMeta(first);
    }
  }, [categoriesData, selectedCategory]);

  // Prefetch folders on category hover
  const handleCategoryHover = (entityType: string) => {
    queryClient.prefetchQuery({
      queryKey: queryKeys.browse.folders(entityType),
      queryFn: async () => {
        const headers = getAuthzClient().getHeaders();
        const res = await fetch(
          `${API_URL}/browse/categories/${encodeURIComponent(entityType)}/folders`,
          { headers },
        );
        if (!res.ok) throw new Error("Prefetch failed");
        return res.json();
      },
      staleTime: 60_000,
    });
  };

  const handleSelectCategory = (entityType: string) => {
    const meta = categoriesData?.categories?.find((c) => c.entity_type === entityType) ?? null;
    setSelectedCategory(entityType);
    setSelectedCategoryMeta(meta);
    setSelectedFolder(null);
    setDateParent(undefined);
    setFolderFilter("");
  };

  const handleSelectFolder = (folder: TagFolderDTO) => {
    setFolderFilter("");
    if (folder.has_children) {
      setDateParent(folder.tag_value);
      setSelectedFolder(null);
    } else {
      setSelectedFolder(folder);
    }
  };

  const handleBreadcrumbNavigate = (level: "root" | "category" | "dateParent") => {
    setFolderFilter("");
    if (level === "root") {
      setSelectedCategory(null);
      setSelectedCategoryMeta(null);
      setSelectedFolder(null);
      setDateParent(undefined);
    } else if (level === "category") {
      setSelectedFolder(null);
      setDateParent(undefined);
    } else if (level === "dateParent") {
      setSelectedFolder(null);
    }
  };

  // ── Table templates (reused from original) ──
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

  const isEmpty = !tableLoading && (!artifacts || artifacts.length === 0) && !tableError;

  // Determine current browse depth
  const showFolderArtifacts = !!selectedFolder;
  const showFolders = !!selectedCategory && !showFolderArtifacts;

  return (
    <div>
      <PageHeader
        icon={FileText}
        title="Documents"
        subtitle="Manage your uploaded documents"
        actions={
          <div className="flex items-center gap-3">
            <SelectButton
              value={viewMode}
              options={VIEW_MODES}
              onChange={(e) => {
                if (e.value) setViewMode(e.value);
              }}
            />
            <Link href={`/${workspace}/documents/upload`}>
              <Button label="Upload" icon="pi pi-upload" />
            </Link>
          </div>
        }
      />

      {tableError && viewMode === "table" && (
        <div className="mb-4">
          <Message
            severity="error"
            text="Failed to load documents. Is the backend running?"
          />
        </div>
      )}

      {viewMode === "browse" ? (
        <div className="space-y-5">
          {/* Breadcrumb */}
          {selectedCategory && (
            <BrowseBreadcrumb
              category={selectedCategoryMeta}
              folder={selectedFolder}
              dateParent={dateParent}
              onNavigate={handleBreadcrumbNavigate}
            />
          )}

          {/* Category bar */}
          <CategoryBar
            categories={categoriesData?.categories}
            selected={selectedCategory}
            onSelect={handleSelectCategory}
            onHover={handleCategoryHover}
            isLoading={categoriesLoading}
          />

          {/* Folder filter */}
          {showFolders && !foldersLoading && (foldersData?.folders?.length ?? 0) > 5 && (
            <IconField iconPosition="left" className="max-w-xs">
              <InputIcon className="pi pi-filter" />
              <InputText
                value={folderFilter}
                onChange={(e) => setFolderFilter(e.target.value)}
                placeholder="Filter folders..."
                className="w-full"
              />
            </IconField>
          )}

          {/* Folder grid or artifact list */}
          {showFolderArtifacts ? (
            <FolderArtifactList
              artifacts={folderArtifacts}
              workspace={workspace}
              isLoading={folderArtifactsLoading}
            />
          ) : showFolders ? (
            <FolderGrid
              folders={filteredFolders}
              onSelect={handleSelectFolder}
              isLoading={foldersLoading}
            />
          ) : (
            !categoriesLoading && (
              <EmptyState
                icon={FileText}
                title="Select a category"
                description="Choose a category above to browse documents by tag."
              />
            )
          )}
        </div>
      ) : isEmpty ? (
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
          loading={tableLoading}
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
