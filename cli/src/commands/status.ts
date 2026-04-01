import { loadConfig } from "../utils/config.js";
import { getAuthCredentials, authHeaders } from "../api/client.js";
import { findArtifactByFilename } from "../utils/artifact-lookup.js";
import * as log from "../utils/logger.js";
import pc from "picocolors";

interface StatusOptions {
  id?: string;
  limit: string;
  json?: boolean;
  apiUrl?: string;
}

interface ArtifactResponse {
  artifact_id: string;
  source_filename: string | null;
  pages: Array<{ page_id: string }> | string[] | null;
}

interface TemporalWorkflowInfo {
  workflow_id: string;
  status: string;
  started_at: string | null;
  closed_at: string | null;
}

interface WorkflowStatusMap {
  entity_id: string;
  workflows: Record<string, TemporalWorkflowInfo>;
}

const STATUS_COLORS: Record<string, (s: string) => string> = {
  COMPLETED: pc.green,
  RUNNING: pc.yellow,
  FAILED: pc.red,
  TIMED_OUT: pc.red,
  NOT_FOUND: pc.dim,
};

function colorStatus(status: string): string {
  const fn = STATUS_COLORS[status] || pc.white;
  return fn(status);
}

export async function statusCommand(
  filename: string | undefined,
  opts: StatusOptions,
): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  // If --id is provided, use it directly
  if (opts.id) {
    await showArtifactStatus(apiUrl, creds, opts.id, opts);
    return;
  }

  // If a filename is given, find the artifact by filename
  if (filename) {
    const artifactId = await findArtifactByFilename(apiUrl, creds, filename);
    if (!artifactId) {
      log.error(`No artifact found with filename "${filename}"`);
      process.exit(1);
    }
    await showArtifactStatus(apiUrl, creds, artifactId, opts);
    return;
  }

  // No filename — show status of recent artifacts
  await showRecentStatus(apiUrl, creds, opts);
}


async function showArtifactStatus(
  apiUrl: string,
  creds: { idp_token: string; authz_token: string },
  artifactId: string,
  opts: StatusOptions,
): Promise<void> {
  const resp = await fetch(`${apiUrl}/artifacts/${artifactId}/workflows`, {
    headers: authHeaders(creds),
  });

  if (!resp.ok) {
    log.error(`Failed to get workflow status: ${resp.status}`);
    process.exit(1);
  }

  const data = (await resp.json()) as WorkflowStatusMap;

  if (opts.json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  // Also get artifact details for the filename
  const detailResp = await fetch(`${apiUrl}/artifacts/${artifactId}`, {
    headers: authHeaders(creds),
  });
  let filename = artifactId;
  if (detailResp.ok) {
    const detail = (await detailResp.json()) as ArtifactResponse;
    filename = detail.source_filename || artifactId;
  }

  console.log(`\n${pc.bold(filename)}`);
  console.log("─".repeat(60));

  const workflows = Object.entries(data.workflows);
  if (workflows.length === 0) {
    log.info("No workflows found for this artifact.");
    return;
  }

  for (const [name, info] of workflows) {
    const status = colorStatus(info.status);
    const shortName = name.replace(`-${artifactId}`, "").replace(/-/g, " ");
    let timing = "";

    if (info.started_at && info.closed_at) {
      const ms =
        new Date(info.closed_at).getTime() - new Date(info.started_at).getTime();
      timing = pc.dim(` (${(ms / 1000).toFixed(1)}s)`);
    } else if (info.started_at && info.status === "RUNNING") {
      const ms = Date.now() - new Date(info.started_at).getTime();
      timing = pc.dim(` (${(ms / 1000).toFixed(0)}s ago)`);
    }

    console.log(`  ${shortName.padEnd(30)} ${status}${timing}`);
  }
  console.log("");
}

async function showRecentStatus(
  apiUrl: string,
  creds: { idp_token: string; authz_token: string },
  opts: StatusOptions,
): Promise<void> {
  const limit = parseInt(opts.limit, 10);

  const params = new URLSearchParams({
    skip: "0",
    limit: String(limit),
    sort_by: "updated_at",
    sort_order: "-1",
  });

  const resp = await fetch(`${apiUrl}/artifacts?${params}`, {
    headers: authHeaders(creds),
  });

  if (!resp.ok) {
    log.error(`Failed to list artifacts: ${resp.status}`);
    process.exit(1);
  }

  const artifacts = (await resp.json()) as ArtifactResponse[];

  if (artifacts.length === 0) {
    log.info("No documents found.");
    return;
  }

  console.log("");

  for (const artifact of artifacts) {
    const wfResp = await fetch(
      `${apiUrl}/artifacts/${artifact.artifact_id}/workflows`,
      { headers: authHeaders(creds) },
    );

    const filename = artifact.source_filename || artifact.artifact_id;
    const pageCount = artifact.pages ? artifact.pages.length : 0;

    if (!wfResp.ok) {
      console.log(`  ${filename.padEnd(40)} ${pc.dim("(status unavailable)")}`);
      continue;
    }

    const data = (await wfResp.json()) as WorkflowStatusMap;
    const workflows = Object.values(data.workflows);

    const running = workflows.filter((w) => w.status === "RUNNING").length;
    const failed = workflows.filter((w) => w.status === "FAILED").length;
    const completed = workflows.filter((w) => w.status === "COMPLETED").length;
    const total = workflows.length;

    let badge: string;
    if (failed > 0) {
      badge = pc.red(`${failed} failed`);
    } else if (running > 0) {
      badge = pc.yellow(`processing (${running} running)`);
    } else if (completed === total && total > 0) {
      badge = pc.green("done");
    } else {
      badge = pc.dim("pending");
    }

    console.log(
      `  ${truncate(filename, 40).padEnd(42)} ${String(pageCount).padEnd(4)}pg  ${badge}`,
    );
  }

  console.log(`\n${artifacts.length} document(s).`);
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}
