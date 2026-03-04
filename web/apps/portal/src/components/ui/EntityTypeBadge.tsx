import { FileText, BookOpen, Atom } from "lucide-react";
import type { LucideIcon } from "lucide-react";

type EntityType = "artifact" | "page" | "compound";

const CONFIG: Record<
  EntityType,
  { icon: LucideIcon; label: string; bg: string; text: string }
> = {
  artifact: {
    icon: FileText,
    label: "Document",
    bg: "bg-blue-50 dark:bg-blue-500/10",
    text: "text-blue-700 dark:text-blue-400",
  },
  page: {
    icon: BookOpen,
    label: "Page",
    bg: "bg-violet-50 dark:bg-violet-500/10",
    text: "text-violet-700 dark:text-violet-400",
  },
  compound: {
    icon: Atom,
    label: "Compound",
    bg: "bg-emerald-50 dark:bg-emerald-500/10",
    text: "text-emerald-700 dark:text-emerald-400",
  },
};

interface EntityTypeBadgeProps {
  type: EntityType;
  className?: string;
}

export function EntityTypeBadge({ type, className = "" }: EntityTypeBadgeProps) {
  const config = CONFIG[type] || CONFIG.artifact;
  const Icon = config.icon;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${config.bg} ${config.text} ${className}`}
    >
      <Icon className="h-3 w-3" />
      {config.label}
    </span>
  );
}
