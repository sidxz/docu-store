/**
 * Duar-hosted self-serve onboarding links.
 * Contract: identity-service docs/guide/self-serve.md — `return_to` must be an
 * allowed origin of the service app and a page that starts sign-in.
 */
export function onboardUrl(duarUrl: string, appUrl: string): string {
  return `${duarUrl}/onboard?return_to=${encodeURIComponent(`${appUrl}/login`)}`;
}

export function inviteUrl(duarUrl: string, appUrl: string, workspaceId: string): string {
  const qs = new URLSearchParams({ workspace: workspaceId, return_to: `${appUrl}/login` });
  return `${duarUrl}/onboard/invites?${qs.toString()}`;
}
