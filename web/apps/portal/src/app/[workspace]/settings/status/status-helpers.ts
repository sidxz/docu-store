/** Shared helpers for the status dashboard. */

export function fmtUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export function statusColor(status: string): string {
  switch (status) {
    case "healthy":
    case "online":
      return "text-ds-success";
    case "degraded":
      return "text-amber-500";
    case "unhealthy":
    case "offline":
      return "text-ds-error";
    case "disabled":
      return "text-text-muted";
    default:
      return "text-text-muted";
  }
}

export function statusBg(status: string): string {
  switch (status) {
    case "healthy":
    case "online":
      return "bg-emerald-500/10 border-emerald-500/20";
    case "degraded":
      return "bg-amber-500/10 border-amber-500/20";
    case "unhealthy":
    case "offline":
      return "bg-red-500/10 border-red-500/20";
    default:
      return "bg-surface-elevated border-border-default";
  }
}

export function statusDot(status: string): string {
  switch (status) {
    case "healthy":
    case "online":
      return "bg-emerald-500";
    case "degraded":
      return "bg-amber-500";
    case "unhealthy":
    case "offline":
      return "bg-red-500";
    case "disabled":
      return "bg-gray-400";
    default:
      return "bg-gray-400";
  }
}

export function statusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function timeAgo(isoString: string): string {
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
