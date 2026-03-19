import { ChevronRight, LayoutGrid } from "lucide-react";

interface BrowseBreadcrumbProps {
  category?: { entity_type: string; display_name: string } | null;
  folder?: { tag_value: string; display_name: string } | null;
  dateParent?: string;
  onNavigate: (level: "root" | "category" | "dateParent") => void;
}

export function BrowseBreadcrumb({
  category,
  folder,
  dateParent,
  onNavigate,
}: BrowseBreadcrumbProps) {
  if (!category) return null;

  return (
    <nav className="flex items-center gap-1 text-xs">
      <button
        onClick={() => onNavigate("root")}
        className="inline-flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 text-text-muted transition-colors hover:text-accent-text"
      >
        <LayoutGrid className="h-3 w-3" />
        All
      </button>

      <ChevronRight className="h-3 w-3 text-text-muted/50" />
      <button
        onClick={() => onNavigate("category")}
        className={`cursor-pointer rounded px-1.5 py-0.5 transition-colors ${
          !folder && !dateParent
            ? "font-medium text-text-primary"
            : "text-text-muted hover:text-accent-text"
        }`}
      >
        {category.display_name}
      </button>

      {dateParent && (
        <>
          <ChevronRight className="h-3 w-3 text-text-muted/50" />
          {folder ? (
            <button
              onClick={() => onNavigate("dateParent")}
              className="cursor-pointer rounded px-1.5 py-0.5 text-text-muted transition-colors hover:text-accent-text"
            >
              {dateParent}
            </button>
          ) : (
            <span className="px-1.5 py-0.5 font-medium text-text-primary">
              {dateParent}
            </span>
          )}
        </>
      )}

      {folder && (
        <>
          <ChevronRight className="h-3 w-3 text-text-muted/50" />
          <span className="px-1.5 py-0.5 font-medium text-text-primary">
            {folder.display_name}
          </span>
        </>
      )}
    </nav>
  );
}
