"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { IconField } from "primereact/iconfield";
import { InputIcon } from "primereact/inputicon";
import { InputText } from "primereact/inputtext";
import { Message } from "primereact/message";
import { FileText, Grid3X3, List } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import type { TagCategoryDTO, TagFolderDTO } from "@docu-store/types";
import { useArtifacts } from "@/hooks/use-artifacts";
import { useTagCategories, useTagFolders, useFolderArtifacts } from "@/hooks/use-browse";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { ViewToggle } from "@/components/ui/ViewToggle";
import { LinkButton } from "@/components/ui/LinkButton";
import { CategoryBar } from "@/components/browse/CategoryBar";
import { FolderGrid } from "@/components/browse/FolderGrid";
import { FolderArtifactList } from "@/components/browse/FolderArtifactList";
import { BrowseBreadcrumb } from "@/components/browse/BrowseBreadcrumb";
import { DocumentsTableView } from "@/components/documents/DocumentsTableView";
import { queryKeys } from "@/lib/query-keys";
import { authFetchJson } from "@/lib/auth-fetch";

type ViewMode = "browse" | "table";

const VIEW_MODES = [
  { value: "browse" as ViewMode, icon: Grid3X3, label: "Browse by category" },
  { value: "table" as ViewMode, icon: List, label: "Table view" },
];

export default function DocumentsPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const queryClient = useQueryClient();

  const [viewMode, setViewMode] = useState<ViewMode>("browse");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedCategoryMeta, setSelectedCategoryMeta] = useState<TagCategoryDTO | null>(null);
  const [selectedFolder, setSelectedFolder] = useState<TagFolderDTO | null>(null);
  const [dateParent, setDateParent] = useState<string | undefined>();
  const [folderFilter, setFolderFilter] = useState("");

  const { data: artifacts, isLoading: tableLoading, error: tableError } = useArtifacts();
  const { data: rawCategoriesData, isLoading: categoriesLoading } = useTagCategories();

  // Ensure "target" category is always visible even if the API doesn't return it
  const categoriesData = useMemo(() => {
    if (!rawCategoriesData) return rawCategoriesData;
    const cats = rawCategoriesData.categories;
    const hasTarget = cats.some((c) => c.entity_type === "target");
    if (hasTarget) return rawCategoriesData;
    return {
      ...rawCategoriesData,
      categories: [
        ...cats,
        { entity_type: "target", display_name: "Target", artifact_count: 0, distinct_count: 0 },
      ],
    };
  }, [rawCategoriesData]);
  const { data: foldersData, isLoading: foldersLoading } = useTagFolders(
    selectedCategory,
    dateParent,
  );
  const { data: folderArtifacts, isLoading: folderArtifactsLoading } = useFolderArtifacts(
    selectedCategory,
    selectedFolder?.tag_value ?? null,
  );

  const filteredFolders = useMemo(() => {
    const folders = foldersData?.folders;
    if (!folders || !folderFilter.trim()) return folders;
    const q = folderFilter.trim().toLowerCase();
    return folders.filter((f) => f.display_name.toLowerCase().includes(q));
  }, [foldersData?.folders, folderFilter]);

  useEffect(() => {
    if (categoriesData?.categories?.length && !selectedCategory) {
      const first = categoriesData.categories[0];
      setSelectedCategory(first.entity_type);
      setSelectedCategoryMeta(first);
    }
  }, [categoriesData, selectedCategory]);

  const handleCategoryHover = (entityType: string) => {
    queryClient.prefetchQuery({
      queryKey: queryKeys.browse.folders(entityType),
      queryFn: () =>
        authFetchJson(`/browse/categories/${encodeURIComponent(entityType)}/folders`),
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

  const isEmpty = !tableLoading && (!artifacts || artifacts.length === 0) && !tableError;
  const showFolderArtifacts = !!selectedFolder;
  const showFolders = !!selectedCategory && !showFolderArtifacts;

  return (
    <div>
      <PageHeader
        icon={FileText}
        title="Documents"
        subtitle="Manage your uploaded documents"
        actions={
          <div className="flex items-center gap-2">
            <ViewToggle value={viewMode} options={VIEW_MODES} onChange={setViewMode} />
            <LinkButton href={`/${workspace}/documents/upload`} label="Upload" icon="pi pi-upload" />
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
        <div className="space-y-4">
          <div className="space-y-3">
            <CategoryBar
              categories={categoriesData?.categories}
              selected={selectedCategory}
              onSelect={handleSelectCategory}
              onHover={handleCategoryHover}
              isLoading={categoriesLoading}
            />

            {showFolders && (
              <div className="flex items-center justify-between gap-4">
                <BrowseBreadcrumb
                  category={selectedCategoryMeta}
                  folder={selectedFolder}
                  dateParent={dateParent}
                  onNavigate={handleBreadcrumbNavigate}
                />
                {!foldersLoading && (foldersData?.folders?.length ?? 0) > 5 && (
                  <IconField iconPosition="left" className="w-48 shrink-0">
                    <InputIcon className="pi pi-search" />
                    <InputText
                      value={folderFilter}
                      onChange={(e) => setFolderFilter(e.target.value)}
                      placeholder="Filter..."
                    />
                  </IconField>
                )}
              </div>
            )}

            {showFolderArtifacts && (
              <BrowseBreadcrumb
                category={selectedCategoryMeta}
                folder={selectedFolder}
                dateParent={dateParent}
                onNavigate={handleBreadcrumbNavigate}
              />
            )}
          </div>

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
              entityType={selectedCategory ?? undefined}
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
            <LinkButton
              href={`/${workspace}/documents/upload`}
              label="Upload Document"
              icon="pi pi-upload"
            />
          }
        />
      ) : (
        <DocumentsTableView
          artifacts={artifacts ?? []}
          workspace={workspace}
          isLoading={tableLoading}
        />
      )}
    </div>
  );
}
