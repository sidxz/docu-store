import { ChevronRight } from "lucide-react";

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
  return (
    <nav className="flex items-center gap-1 text-sm">
      <button
        onClick={() => onNavigate("root")}
        className={`cursor-pointer rounded px-1.5 py-0.5 transition-colors ${
          !category
            ? "font-semibold text-text-primary"
            : "text-text-secondary hover:text-accent-text"
        }`}
      >
        All Categories
      </button>

      {category && (
        <>
          <ChevronRight className="h-3.5 w-3.5 text-text-muted" />
          <button
            onClick={() => onNavigate("category")}
            className={`cursor-pointer rounded px-1.5 py-0.5 transition-colors ${
              !folder && !dateParent
                ? "font-semibold text-text-primary"
                : "text-text-secondary hover:text-accent-text"
            }`}
          >
            {category.display_name}
          </button>
        </>
      )}

      {dateParent && !folder && (
        <>
          <ChevronRight className="h-3.5 w-3.5 text-text-muted" />
          <span className="px-1.5 py-0.5 font-semibold text-text-primary">
            {dateParent}
          </span>
        </>
      )}

      {folder && (
        <>
          {dateParent && (
            <>
              <ChevronRight className="h-3.5 w-3.5 text-text-muted" />
              <button
                onClick={() => onNavigate("dateParent")}
                className="cursor-pointer rounded px-1.5 py-0.5 text-text-secondary transition-colors hover:text-accent-text"
              >
                {dateParent}
              </button>
            </>
          )}
          <ChevronRight className="h-3.5 w-3.5 text-text-muted" />
          <span className="px-1.5 py-0.5 font-semibold text-text-primary">
            {folder.display_name}
          </span>
        </>
      )}
    </nav>
  );
}
