import { loadConfig } from "../utils/config.js";
import { getAuthCredentials, authHeaders } from "../api/client.js";
import { extractApiError } from "../utils/api-error.js";
import * as log from "../utils/logger.js";
import pc from "picocolors";

interface DashboardOptions {
  json?: boolean;
  apiUrl?: string;
}

interface DashboardStats {
  total_artifacts: number;
  total_pages: number;
  total_compounds: number;
  with_summary: number;
}

export async function dashboardCommand(opts: DashboardOptions): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  const resp = await fetch(`${apiUrl}/dashboard/stats`, {
    headers: authHeaders(creds),
  });

  if (!resp.ok) {
    log.error(`Failed to get dashboard stats: ${await extractApiError(resp)}`);
    process.exit(1);
  }

  const stats = (await resp.json()) as DashboardStats;

  if (opts.json) {
    console.log(JSON.stringify(stats, null, 2));
    return;
  }

  console.log(`\n${pc.bold("Workspace Dashboard")}`);
  console.log("─".repeat(40));
  console.log(`  Documents    ${pc.cyan(String(stats.total_artifacts))}`);
  console.log(`  Pages        ${pc.cyan(String(stats.total_pages))}`);
  console.log(`  Compounds    ${pc.cyan(String(stats.total_compounds))}`);
  console.log(`  Summarized   ${pc.green(String(stats.with_summary))} / ${stats.total_artifacts}`);
  console.log("");
}
