const CLI_ORIGIN = "docu-cli://localhost";

export interface SentinelUser {
  id: string;
  email: string;
  name: string;
}

export interface SentinelWorkspace {
  id: string;
  slug: string;
  name: string;
  role: string;
}

export interface ResolveResult {
  user: SentinelUser;
  workspaces?: SentinelWorkspace[];
  workspace?: SentinelWorkspace;
  authz_token?: string;
  expires_in?: number;
}

export class SentinelError extends Error {
  constructor(
    message: string,
    public statusCode: number,
  ) {
    super(message);
    this.name = "SentinelError";
  }
}

/**
 * Call Sentinel's /authz/resolve endpoint using Origin-based auth (no service key).
 *
 * - Without workspace_id: returns user + available workspaces
 * - With workspace_id: returns user + workspace + authz_token
 */
export async function resolve(
  sentinelUrl: string,
  idpToken: string,
  provider: string,
  workspaceId?: string,
): Promise<ResolveResult> {
  const body: Record<string, string> = {
    idp_token: idpToken,
    provider,
  };
  if (workspaceId) {
    body.workspace_id = workspaceId;
  }

  const resp = await fetch(`${sentinelUrl.replace(/\/$/, "")}/authz/resolve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: CLI_ORIGIN,
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    let detail: string;
    try {
      const err = await resp.json();
      detail = (err as { detail?: string }).detail || resp.statusText;
    } catch {
      detail = resp.statusText;
    }
    throw new SentinelError(detail, resp.status);
  }

  return (await resp.json()) as ResolveResult;
}

/**
 * Mint an authz token via the docu-store backend's /auth/mint endpoint.
 *
 * Since Sentinel 0.11.0, minting requires a service key, which a CLI must not
 * hold. The backend holds it and forwards to Sentinel's /authz/resolve. Discovery
 * (workspace listing, no workspace_id) still uses `resolve()` against Sentinel
 * directly via Origin auth; only the credential-issuance step is routed here.
 */
export async function mint(
  apiUrl: string,
  idpToken: string,
  provider: string,
  workspaceId: string,
  nonce?: string,
): Promise<ResolveResult> {
  const body: Record<string, string> = {
    idp_token: idpToken,
    provider,
    workspace_id: workspaceId,
  };
  if (nonce) {
    body.nonce = nonce;
  }

  const resp = await fetch(`${apiUrl.replace(/\/$/, "")}/auth/mint`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    let detail: string;
    try {
      const err = await resp.json();
      detail = (err as { detail?: string }).detail || resp.statusText;
    } catch {
      detail = resp.statusText;
    }
    throw new SentinelError(detail, resp.status);
  }

  return (await resp.json()) as ResolveResult;
}
