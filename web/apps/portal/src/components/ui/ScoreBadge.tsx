interface ScoreBadgeProps {
  score: number;
  variant?: "bar" | "pill";
  className?: string;
}

function getScoreColor(score: number): string {
  if (score >= 0.8) return "bg-score-excellent";
  if (score >= 0.6) return "bg-score-good";
  if (score >= 0.4) return "bg-score-fair";
  return "bg-score-poor";
}

function getScoreTextColor(score: number): string {
  if (score >= 0.8) return "text-score-excellent";
  if (score >= 0.6) return "text-score-good";
  if (score >= 0.4) return "text-score-fair";
  return "text-score-poor";
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
