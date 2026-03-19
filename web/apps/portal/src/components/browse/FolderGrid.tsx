import { Folder, Calendar, ChevronRight } from "lucide-react";
import { Skeleton } from "primereact/skeleton";
import type { TagFolderDTO } from "@docu-store/types";

interface FolderGridProps {
  folders: TagFolderDTO[] | undefined;
  onSelect: (folder: TagFolderDTO) => void;
  isLoading?: boolean;
  entityType?: string;
}

export function FolderGrid({ folders, onSelect, isLoading, entityType }: FolderGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} height="3.5rem" borderRadius="0.75rem" />
        ))}
      </div>
    );
  }

  if (!folders?.length) {
    return (
      <p className="py-10 text-center text-sm text-text-muted">
        No items in this category.
      </p>
    );
  }

  const FolderIcon = entityType === "date" ? Calendar : Folder;

  return (
    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {folders.map((folder) => (
        <button
          key={folder.tag_value}
          onClick={() => onSelect(folder)}
          className="group flex cursor-pointer items-center gap-3 rounded-xl border border-border-default bg-surface-elevated px-4 py-3 text-left transition-all duration-150 hover:border-accent/30 hover:shadow-ds-sm active:scale-[0.99]"
        >
          <FolderIcon className="h-4 w-4 shrink-0 text-text-muted transition-colors group-hover:text-accent-text" />
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-text-primary">
            {folder.display_name}
          </span>
          <span className="shrink-0 text-xs tabular-nums text-text-muted">
            {folder.artifact_count}
          </span>
          {folder.has_children && (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-text-muted transition-transform group-hover:translate-x-0.5" />
          )}
        </button>
      ))}
    </div>
  );
}
