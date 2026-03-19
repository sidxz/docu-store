import type { LucideIcon } from "lucide-react";

interface ViewToggleOption<T extends string> {
  value: T;
  icon: LucideIcon;
  label: string;
}

interface ViewToggleProps<T extends string> {
  value: T;
  options: ViewToggleOption<T>[];
  onChange: (value: T) => void;
}

export function ViewToggle<T extends string>({
  value,
  options,
  onChange,
}: ViewToggleProps<T>) {
  return (
    <div
      className="inline-flex rounded-lg border border-border-default bg-surface-elevated p-0.5"
      role="radiogroup"
    >
      {options.map((opt) => {
        const Icon = opt.icon;
        const isActive = value === opt.value;
        return (
          <button
            key={opt.value}
            role="radio"
            aria-checked={isActive}
            aria-label={opt.label}
            title={opt.label}
            onClick={() => onChange(opt.value)}
            className={`inline-flex cursor-pointer items-center justify-center rounded-md px-2 py-1.5 transition-all duration-150 ${
              isActive
                ? "bg-accent text-white shadow-ds-sm"
                : "text-text-muted hover:text-text-primary"
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
          </button>
        );
      })}
    </div>
  );
}
