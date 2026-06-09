import {
  isExpired,
  loadCredentials,
  saveCredentials,
  type Credentials,
} from "../auth/credentials.js";
import { refreshGoogleToken } from "../auth/google.js";
import { mint, SentinelError } from "../auth/sentinel.js";
import { loadConfig } from "../utils/config.js";
import * as log from "../utils/logger.js";

/** Check if the IdP token itself has expired (Google ~1hr). */
function isIdpTokenExpired(creds: Credentials): boolean {
  if (!creds.idp_token_expires_at) return false; // GitHub tokens don't expire
  return Date.now() / 1000 > creds.idp_token_expires_at - 60; // 60s buffer
}

/**
 * Ensure the IdP token is fresh. For Google, uses refresh_token to get a new id_token.
 * Returns true if the IdP token was refreshed (meaning authz token also needs refresh).
 */
async function ensureFreshIdpToken(creds: Credentials): Promise<boolean> {
  if (!isIdpTokenExpired(creds)) return false;

  if (!creds.refresh_token || !creds.google_client_id || !creds.google_client_secret) {
    log.error("Google ID token expired and no refresh token available. Run: docu login");
    process.exit(1);
  }

  log.info("Refreshing Google ID token...");
  try {
    const result = await refreshGoogleToken(creds.refresh_token, creds.google_client_id, creds.google_client_secret);
    creds.idp_token = result.id_token;
    creds.idp_token_expires_at = Date.now() / 1000 + result.expires_in;
    saveCredentials(creds);
    return true;
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    log.error(`Google token refresh failed: ${msg}. Run: docu login`);
    process.exit(1);
  }
}

/**
 * Get a valid set of credentials, auto-refreshing tokens as needed.
 * For Google: refreshes IdP token (via refresh_token) then authz token.
 * For GitHub: IdP token never expires, only refreshes authz token.
 */
export async function getAuthCredentials(): Promise<Credentials> {
  const creds = loadCredentials();
  if (!creds) {
    log.error("Not logged in. Run: docu login");
    process.exit(1);
  }

  // Step 1: Ensure IdP token is fresh (Google only)
  const idpRefreshed = await ensureFreshIdpToken(creds);

  // Step 2: Refresh authz token if expired or if IdP token was just refreshed
  if (!isExpired(creds) && !idpRefreshed) {
    return creds;
  }

  if (!creds.idp_token) {
    log.error("Token expired and no IdP token for refresh. Run: docu login");
    process.exit(1);
  }

  log.info("Refreshing authorization token...");
  const config = loadConfig();

  try {
    const result = await mint(
      config.api_url,
      creds.idp_token,
      creds.provider,
      creds.workspace_id,
    );

    if (!result.authz_token || !result.expires_in) {
      log.error("Token refresh failed. Run: docu login");
      process.exit(1);
    }

    creds.authz_token = result.authz_token;
    creds.expires_at = Date.now() / 1000 + result.expires_in;
    saveCredentials(creds);
    return creds;
  } catch (err) {
    if (err instanceof SentinelError) {
      log.error(`Token refresh failed: ${err.message}. Run: docu login`);
    } else {
      log.error(`Token refresh failed. Run: docu login`);
    }
    process.exit(1);
  }
}

/** Build the dual-token auth headers matching @sentinel-auth/js getHeaders(). */
export function authHeaders(creds: Credentials): Record<string, string> {
  return {
    Authorization: `Bearer ${creds.idp_token}`,
    "X-Authz-Token": creds.authz_token,
  };
}

/** Upload a file via multipart POST to /artifacts/upload. */
export async function uploadFile(
  apiUrl: string,
  creds: Credentials,
  filePath: string,
  fileName: string,
  fileData: Uint8Array,
  artifactType: string,
  visibility: string,
): Promise<{ artifact_id: string; pages: unknown[] }> {
  const formData = new FormData();
  const mimeType = fileName.toLowerCase().endsWith(".pdf")
    ? "application/pdf"
    : "application/octet-stream";
  formData.append("file", new Blob([fileData], { type: mimeType }), fileName);
  formData.append("artifact_type", artifactType);
  formData.append("visibility", visibility);

  const resp = await fetch(`${apiUrl}/artifacts/upload`, {
    method: "POST",
    headers: authHeaders(creds),
    body: formData,
  });

  if (resp.status === 401) {
    throw new Error("AUTH_EXPIRED");
  }

  if (!resp.ok) {
    let detail: string;
    try {
      const body = await resp.json();
      detail = (body as { detail?: string }).detail || resp.statusText;
    } catch {
      detail = resp.statusText;
    }
    throw new Error(`Upload failed (${resp.status}): ${detail}`);
  }

  return (await resp.json()) as { artifact_id: string; pages: unknown[] };
}

/** Fetch all existing artifact filenames for --resume support. */
export async function listArtifactFilenames(
  apiUrl: string,
  creds: Credentials,
): Promise<Set<string>> {
  const filenames = new Set<string>();
  let skip = 0;
  const limit = 100;

  while (true) {
    const resp = await fetch(
      `${apiUrl}/artifacts?skip=${skip}&limit=${limit}`,
      { headers: authHeaders(creds) },
    );

    if (!resp.ok) {
      throw new Error(`Failed to list artifacts: ${resp.status}`);
    }

    const artifacts = (await resp.json()) as Array<{ source_filename?: string }>;
    if (!artifacts.length) break;

    for (const a of artifacts) {
      if (a.source_filename) {
        filenames.add(a.source_filename);
      }
    }

    if (artifacts.length < limit) break;
    skip += limit;
  }

  return filenames;
}
