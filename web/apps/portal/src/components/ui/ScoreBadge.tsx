interface ScoreBadgeProps {
  score: number;
  variant?: "bar" | "pill";
  className?: string;
}

function getScoreColor(score: number): string {
  if (score >= 0.8) return "bg-emerald-500";
  if (score >= 0.6) return "bg-teal-500";
  if (score >= 0.4) return "bg-amber-500";
  return "bg-red-400";
}

function getScoreTextColor(score: number): string {
  if (score >= 0.8) return "text-emerald-700 dark:text-emerald-400";
  if (score >= 0.6) return "text-teal-700 dark:text-teal-400";
  if (score >= 0.4) return "text-amber-700 dark:text-amber-400";
  return "text-red-700 dark:text-red-400";
}

export function ScoreBadge({
  score,
  variant = "bar",
  className = "",
}: ScoreBadgeProps) {
  const pct = Math.round(score * 100);

  if (variant === "pill") {
    return (
      <span
        className={`inline-flex items-center gap-1 rounded-full border border-border-default px-2 py-0.5 text-xs font-medium ${getScoreTextColor(score)} ${className}`}
      >
        {pct}%
      </span>
    );
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="h-1.5 w-16 rounded-full bg-border-subtle overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${getScoreColor(score)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-medium text-text-secondary">{pct}%</span>
    </div>
  );
}
