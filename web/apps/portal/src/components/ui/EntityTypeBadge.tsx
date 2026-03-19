import { Tag } from "primereact/tag";

type EntityType = "artifact" | "page" | "compound";

const CONFIG: Record<
  EntityType,
  { icon: string; label: string; severity: "info" | "success" | "warning" | "secondary" }
> = {
  artifact: { icon: "pi pi-file", label: "Document", severity: "info" },
  page: { icon: "pi pi-book", label: "Page", severity: "secondary" },
  compound: { icon: "pi pi-sitemap", label: "Compound", severity: "success" },
};

interface EntityTypeBadgeProps {
  type: EntityType;
  className?: string;
}

export function EntityTypeBadge({ type, className = "" }: EntityTypeBadgeProps) {
  const config = CONFIG[type] || CONFIG.artifact;

  return (
    <Tag
      value={config.label}
      severity={config.severity}
      icon={config.icon}
      className={className}
    />
  );
}
