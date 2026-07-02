"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { AlertCircle, FileText, Grid3X3, List, Search, Upload } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import type { TagFolderDTO } from "@docu-store/types";
import { useArtifacts } from "@/hooks/use-artifacts";
import { useTagCategories, useTagFolders, useFolderArtifacts } from "@/hooks/use-browse";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { ViewToggle } from "@/components/ui/ViewToggle";
import { LinkButton } from "@/components/ui/LinkButton";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  // ── Read navigation state from URL ────────────────────────────────────────
  const viewMode = (searchParams.get("view") ?? "browse") as ViewMode;
  const selectedCategory = searchParams.get("cat");
  const dateParent = searchParams.get("dp") ?? undefined;
  const selectedFolderValue = searchParams.get("folder");

  // Transient filter (not in URL — not meaningful to history)
  const [folderFilter, setFolderFilter] = useState("");

  // ── Data fetching ─────────────────────────────────────────────────────────
  const { data: artifacts, isLoading: tableLoading, error: tableError } = useArtifacts();
  const { data: categoriesData, isLoading: categoriesLoading } = useTagCategories();

  // Effective category: URL param, or fall back to first loaded category
  const effectiveCategory = selectedCategory ?? (categoriesData?.categories?.[0]?.entity_type ?? null);

  const { data: foldersData, isLoading: foldersLoading } = useTagFolders(
    effectiveCategory,
    dateParent,
  );
  const { data: folderArtifacts, isLoading: folderArtifactsLoading } = useFolderArtifacts(
    effectiveCategory,
    selectedFolderValue,
  );

  // Derive category metadata from loaded data
  const selectedCategoryMeta = useMemo(
    () => categoriesData?.categories?.find((c) => c.entity_type === effectiveCategory) ?? null,
    [categoriesData, effectiveCategory],
  );

  // Derive folder display info from loaded folders data
  const selectedFolderMeta = useMemo(() => {
    if (!selectedFolderValue) return null;
    const match = foldersData?.folders?.find((f) => f.tag_value === selectedFolderValue);
    return match
      ? { tag_value: match.tag_value, display_name: match.display_name }
      : { tag_value: selectedFolderValue, display_name: selectedFolderValue };
  }, [selectedFolderValue, foldersData]);

  const filteredFolders = useMemo(() => {
    const folders = foldersData?.folders;
    if (!folders || !folderFilter.trim()) return folders;
    const q = folderFilter.trim().toLowerCase();
    return folders.filter((f) => f.display_name.toLowerCase().includes(q));
  }, [foldersData?.folders, folderFilter]);

  // ── URL navigation helpers ────────────────────────────────────────────────

  const buildUrl = (params: Record<string, string | undefined>) => {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) sp.set(k, v);
    }
    const qs = sp.toString();
    return `/${workspace}/documents${qs ? `?${qs}` : ""}`;
  };

  const handleViewModeChange = (mode: ViewMode) => {
    if (mode === "table") {
      router.push(buildUrl({ view: "table" }));
    } else {
      router.push(buildUrl({})); // browse is default, no params needed
    }
  };

  const handleSelectCategory = (entityType: string) => {
    setFolderFilter("");
    router.push(buildUrl({ cat: entityType }));
  };

  const handleCategoryHover = (entityType: string) => {
    queryClient.prefetchQuery({
      queryKey: queryKeys.browse.folders(entityType),
      queryFn: () =>
        authFetchJson(`/browse/categories/${encodeURIComponent(entityType)}/folders`),
      staleTime: 60_000,
    });
  };

  const handleSelectFolder = (folder: TagFolderDTO) => {
    setFolderFilter("");
    if (folder.has_children) {
      // Drill into date parent (e.g., year → months)
      router.push(buildUrl({
        cat: effectiveCategory ?? undefined,
        dp: folder.tag_value,
      }));
    } else {
      // Show artifacts in this folder
      router.push(buildUrl({
        cat: effectiveCategory ?? undefined,
        dp: dateParent,
        folder: folder.tag_value,
      }));
    }
  };

  const handleBreadcrumbNavigate = (level: "root" | "category" | "dateParent") => {
    setFolderFilter("");
    if (level === "root") {
      router.push(buildUrl({}));
    } else if (level === "category") {
      router.push(buildUrl({ cat: effectiveCategory ?? undefined }));
    } else if (level === "dateParent") {
      router.push(buildUrl({
        cat: effectiveCategory ?? undefined,
        dp: dateParent,
      }));
    }
  };

  const isEmpty = !tableLoading && (!artifacts || artifacts.length === 0) && !tableError;
  const showFolderArtifacts = !!selectedFolderValue;
  const showFolders = !!(effectiveCategory) && !showFolderArtifacts;

  return (
    <div>
      <PageHeader
        icon={FileText}
        title="Documents"
        subtitle="Manage your uploaded documents"
        actions={
          <div className="flex items-center gap-2">
            <ViewToggle value={viewMode} options={VIEW_MODES} onChange={handleViewModeChange} />
            <LinkButton href={`/${workspace}/documents/upload`} label="Upload" icon={Upload} />
          </div>
        }
      />

      {tableError && viewMode === "table" && (
        <Alert variant="destructive" className="mb-4">
          <AlertCircle className="size-4" />
          <AlertDescription>
            Failed to load documents. Is the backend running?
          </AlertDescription>
        </Alert>
      )}

      {viewMode === "browse" ? (
        <div className="space-y-4">
          <div className="space-y-3">
            <CategoryBar
              categories={categoriesData?.categories}
              selected={effectiveCategory}
              onSelect={handleSelectCategory}
              onHover={handleCategoryHover}
              isLoading={categoriesLoading}
            />

            {showFolders && (
              <div className="flex items-center justify-between gap-4">
                <BrowseBreadcrumb
                  category={selectedCategoryMeta}
                  folder={selectedFolderMeta}
                  dateParent={dateParent}
                  onNavigate={handleBreadcrumbNavigate}
                />
                {!foldersLoading && (foldersData?.folders?.length ?? 0) > 5 && (
                  <div className="relative w-48 shrink-0">
                    <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-muted" />
                    <Input
                      className="pl-9"
                      value={folderFilter}
                      onChange={(e) => setFolderFilter(e.target.value)}
                      placeholder="Filter..."
                    />
                  </div>
                )}
              </div>
            )}

            {showFolderArtifacts && (
              <BrowseBreadcrumb
                category={selectedCategoryMeta}
                folder={selectedFolderMeta}
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
              entityType={(effectiveCategory) ?? undefined}
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
              icon={Upload}
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
