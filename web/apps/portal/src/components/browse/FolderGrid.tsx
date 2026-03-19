import { Folder, ChevronRight } from "lucide-react";
import { Skeleton } from "primereact/skeleton";
import type { TagFolderDTO } from "@docu-store/types";

interface FolderGridProps {
  folders: TagFolderDTO[] | undefined;
  onSelect: (folder: TagFolderDTO) => void;
  isLoading?: boolean;
}

export function FolderGrid({ folders, onSelect, isLoading }: FolderGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} height="4.5rem" borderRadius="0.75rem" />
        ))}
      </div>
    );
  }

  if (!folders?.length) {
    return (
      <p className="py-8 text-center text-sm text-text-muted">
        No items in this category.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {folders.map((folder) => (
        <button
          key={folder.tag_value}
          onClick={() => onSelect(folder)}
          className="group flex cursor-pointer items-center gap-3 rounded-xl border border-border-default bg-surface-elevated p-4 text-left transition-colors hover:border-accent-text/40 hover:shadow-ds-sm"
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-light text-accent-text">
            <Folder className="h-4.5 w-4.5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-text-primary group-hover:text-accent-text">
              {folder.display_name}
            </p>
            <p className="text-xs text-text-muted">
              {folder.artifact_count} document{folder.artifact_count !== 1 ? "s" : ""}
            </p>
          </div>
          {folder.has_children && (
            <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" />
          )}
        </button>
      ))}
    </div>
  );
}
