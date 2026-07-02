// NER entity-type → chip style for recent-chat cards. Palette echoes
// EntityTagPanel (compounds emerald, targets amber, diseases rose) but adds
// gene/assay + text colors, so the two maps are intentionally separate.
const STYLES: Record<string, string> = {
  compound: "border-emerald-500/30 text-emerald-700 dark:text-emerald-400",
  compound_name: "border-emerald-500/30 text-emerald-700 dark:text-emerald-400",
  target: "border-amber-500/30 text-amber-700 dark:text-amber-400",
  gene: "border-amber-500/30 text-amber-700 dark:text-amber-400",
  assay: "border-blue-500/30 text-blue-700 dark:text-blue-400",
  disease: "border-rose-500/30 text-rose-700 dark:text-rose-400",
};
const FALLBACK = "border-zinc-400/30 text-zinc-600 dark:text-zinc-400";

export function entityChipClass(type: string): string {
  return STYLES[type] ?? FALLBACK;
}
