/**
 * Low-level analytics helpers.
 * Works in any JS context (React hooks, Zustand stores, plain callbacks).
 */

function getWorkspace(): string {
  if (typeof window === "undefined") return "unknown";
  const segments = window.location.pathname.split("/").filter(Boolean);
  return segments[0] ?? "unknown";
}

export function trackEvent(
  name: string,
  data?: Record<string, string | number>,
): void {
  if (typeof window === "undefined" || !window.umami) return;
  window.umami.track(name, { workspace: getWorkspace(), ...data });
}
