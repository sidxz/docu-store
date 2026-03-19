import { Skeleton } from "primereact/skeleton";
import type { TagCategoryDTO } from "@docu-store/types";

interface CategoryBarProps {
  categories: TagCategoryDTO[] | undefined;
  selected: string | null;
  onSelect: (entityType: string) => void;
  onHover?: (entityType: string) => void;
  isLoading?: boolean;
}

export function CategoryBar({
  categories,
  selected,
  onSelect,
  onHover,
  isLoading,
}: CategoryBarProps) {
  if (isLoading) {
    return (
      <div className="flex gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} width="7rem" height="2rem" borderRadius="0.5rem" />
        ))}
      </div>
    );
  }

  if (!categories?.length) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {categories.map((cat) => {
        const isActive = selected === cat.entity_type;
        return (
          <button
            key={cat.entity_type}
            onClick={() => onSelect(cat.entity_type)}
            onMouseEnter={() => onHover?.(cat.entity_type)}
            className={`inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all duration-150 ${
              isActive
                ? "border-accent bg-accent text-white shadow-ds-sm"
                : "border-border-default bg-surface-elevated text-text-secondary hover:border-border-default/80 hover:bg-surface-sunken hover:text-text-primary"
            }`}
          >
            {cat.display_name}
            <span
              className={`tabular-nums ${
                isActive
                  ? "text-white/70"
                  : "text-text-muted"
              }`}
            >
              {cat.artifact_count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
