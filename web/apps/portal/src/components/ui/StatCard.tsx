import { Skeleton } from "primereact/skeleton";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  trend?: string;
  loading?: boolean;
  accentColor?: string;
}

export function StatCard({
  icon: Icon,
  label,
  value,
  trend,
  loading,
  accentColor,
}: StatCardProps) {
  if (loading) {
    return (
      <div className="rounded-xl border border-border-default bg-surface-elevated p-5">
        <div className="flex items-center justify-between">
          <Skeleton width="5rem" height="0.875rem" />
          <Skeleton width="2.25rem" height="2.25rem" borderRadius="0.5rem" />
        </div>
        <div className="mt-4">
          <Skeleton width="4rem" height="1.75rem" />
        </div>
      </div>
    );
  }

  return (
    <div className="group rounded-xl border border-border-default bg-surface-elevated p-5 transition-all duration-200 hover:shadow-ds hover:border-border-default/80">
      <div className="flex items-center justify-between">
        <span className="text-sm text-text-muted">{label}</span>
        <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${accentColor ?? "bg-accent-light"}`}>
          <Icon className="h-[18px] w-[18px] text-accent-text" />
        </div>
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-2xl font-bold tracking-tight text-text-primary">
          {value}
        </span>
        {trend && (
          <span className="text-xs font-medium text-ds-success">{trend}</span>
        )}
      </div>
    </div>
  );
}
