/**
 * Duar-hosted self-serve onboarding links.
 * Contract: identity-service docs/guide/self-serve.md — `return_to` must be an
 * allowed origin of the service app and a page that starts sign-in. The
 * browser's own origin is used: it already passed Duar's CORS check for
 * /authz/resolve, so it is in `allowed_origins` by construction.
 */
function returnTo(): string {
  return `${window.location.origin}/login`;
}

export function onboardUrl(duarUrl: string): string {
  return `${duarUrl}/onboard?return_to=${encodeURIComponent(returnTo())}`;
}

export function inviteUrl(duarUrl: string, workspaceId: string): string {
  const qs = new URLSearchParams({ workspace: workspaceId, return_to: returnTo() });
  return `${duarUrl}/onboard/invites?${qs.toString()}`;
}
