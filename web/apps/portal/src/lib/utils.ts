import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind class lists, resolving conflicts (shadcn/ui convention). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Extract up to 2 initials from a name string.
 * "John Doe" → "JD", "Alice" → "A", "" → "?"
 */
export function getInitials(name: string | null | undefined): string {
  if (!name) return "?";
  return (
    name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "?"
  );
}

const _compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

/** Compact token count for badges: 1403 → "1.4K", 138458 → "138.5K". */
export function formatTokens(n: number): string {
  return _compact.format(n);
}

/** Relative time for timestamps: "just now", "5m ago", "3h ago", "2d ago", then a date. */
export function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  const s = Math.floor((Date.now() - d.getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
