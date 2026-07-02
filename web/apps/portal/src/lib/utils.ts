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
