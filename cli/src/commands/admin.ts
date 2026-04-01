import { loadConfig } from "../utils/config.js";
import { getAuthCredentials, authHeaders } from "../api/client.js";
import { extractApiError } from "../utils/api-error.js";
import * as log from "../utils/logger.js";
import pc from "picocolors";

interface AdminOptions {
  json?: boolean;
  apiUrl?: string;
  period?: string;
}

async function adminFetch(
  apiUrl: string,
  path: string,
  creds: { idp_token: string; authz_token: string },
  params?: URLSearchParams,
): Promise<unknown> {
  const url = params ? `${apiUrl}${path}?${params}` : `${apiUrl}${path}`;
  const resp = await fetch(url, { headers: authHeaders(creds) });

  if (resp.status === 403) {
    log.error("Admin access required.");
    process.exit(1);
  }

  if (!resp.ok) {
    log.error(`Failed: ${await extractApiError(resp)}`);
    process.exit(1);
  }

  return resp.json();
}

// ── Workflows ────────────────────────────────────────────────────────

export async function adminWorkflowsCommand(opts: AdminOptions): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  const data = (await adminFetch(apiUrl, "/stats/workflows", creds)) as Record<string, unknown>;

  if (opts.json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  console.log(`\n${pc.bold("Workflow Statistics")}`);
  console.log("─".repeat(40));
  for (const [key, value] of Object.entries(data)) {
    console.log(`  ${key.padEnd(25)} ${pc.cyan(String(value))}`);
  }
  console.log("");
}

// ── Pipeline ─────────────────────────────────────────────────────────

export async function adminPipelineCommand(opts: AdminOptions): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  const data = (await adminFetch(apiUrl, "/stats/pipeline", creds)) as Record<string, unknown>;

  if (opts.json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  console.log(`\n${pc.bold("Pipeline Statistics")}`);
  console.log("─".repeat(40));
  for (const [key, value] of Object.entries(data)) {
    console.log(`  ${key.padEnd(25)} ${pc.cyan(String(value))}`);
  }
  console.log("");
}

// ── Vectors ──────────────────────────────────────────────────────────

export async function adminVectorsCommand(opts: AdminOptions): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  const data = (await adminFetch(apiUrl, "/stats/vectors", creds)) as Record<string, unknown>;

  if (opts.json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  console.log(`\n${pc.bold("Vector Store Statistics")}`);
  console.log("─".repeat(40));
  for (const [key, value] of Object.entries(data)) {
    if (typeof value === "object" && value !== null) {
      console.log(`  ${pc.bold(key)}`);
      for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
        console.log(`    ${k.padEnd(23)} ${pc.cyan(String(v))}`);
      }
    } else {
      console.log(`  ${key.padEnd(25)} ${pc.cyan(String(value))}`);
    }
  }
  console.log("");
}

// ── Token usage ──────────────────────────────────────────────────────

export async function adminTokensCommand(opts: AdminOptions): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const period = opts.period || "week";
  const creds = await getAuthCredentials();

  const params = new URLSearchParams({ period });
  const data = (await adminFetch(apiUrl, "/stats/token-usage", creds, params)) as Record<
    string,
    unknown
  >;

  if (opts.json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  console.log(`\n${pc.bold("Token Usage")} (${period})`);
  console.log("─".repeat(40));
  for (const [key, value] of Object.entries(data)) {
    if (typeof value === "number") {
      console.log(`  ${key.padEnd(25)} ${pc.cyan(value.toLocaleString())}`);
    } else {
      console.log(`  ${key.padEnd(25)} ${pc.cyan(String(value))}`);
    }
  }
  console.log("");
}
