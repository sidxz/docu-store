import { Tag } from "primereact/tag";
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
          <Skeleton key={i} width="6rem" height="2.25rem" borderRadius="9999px" />
        ))}
      </div>
    );
  }

  if (!categories?.length) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {categories.map((cat) => {
        const isActive = selected === cat.entity_type;
        return (
          <button
            key={cat.entity_type}
            onClick={() => onSelect(cat.entity_type)}
            onMouseEnter={() => onHover?.(cat.entity_type)}
            className={`inline-flex cursor-pointer items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors ${
              isActive
                ? "border-accent-text bg-accent-light text-accent-text"
                : "border-border-default bg-surface-elevated text-text-secondary hover:border-accent-text/40 hover:text-text-primary"
            }`}
          >
            {cat.display_name}
            <Tag
              value={String(cat.artifact_count)}
              severity={isActive ? "info" : "secondary"}
              rounded
              className="!px-1.5 !py-0 !text-xs"
            />
          </button>
        );
      })}
    </div>
  );
}
