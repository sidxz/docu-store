import { FileText, StickyNote, FlaskConical, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { severityToVariant, type PrimeSeverity } from "@/lib/severity";

type EntityType = "artifact" | "page" | "compound";

const CONFIG: Record<
  EntityType,
  { icon: LucideIcon; label: string; severity: PrimeSeverity }
> = {
  artifact: { icon: FileText, label: "Document", severity: "info" },
  page: { icon: StickyNote, label: "Page", severity: "secondary" },
  compound: { icon: FlaskConical, label: "Compound", severity: "success" },
};

interface EntityTypeBadgeProps {
  type: EntityType;
  className?: string;
}

export function EntityTypeBadge({ type, className = "" }: EntityTypeBadgeProps) {
  const config = CONFIG[type] || CONFIG.artifact;
  const Icon = config.icon;

  return (
    <Badge variant={severityToVariant[config.severity]} className={className}>
      <Icon />
      {config.label}
    </Badge>
  );
}
