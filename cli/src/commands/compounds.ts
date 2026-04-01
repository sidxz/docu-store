import { loadConfig } from "../utils/config.js";
import { getAuthCredentials, authHeaders } from "../api/client.js";
import { extractApiError } from "../utils/api-error.js";
import * as log from "../utils/logger.js";
import pc from "picocolors";

interface CompoundsSearchOptions {
  limit: string;
  threshold: string;
  json?: boolean;
  apiUrl?: string;
}

interface CompoundHit {
  page_id: string;
  artifact_id: string;
  page_index: number;
  score: number;
  canonical_smiles: string | null;
  compound_name: string | null;
  artifact_name: string | null;
}

interface CompoundSearchResponse {
  query_smiles: string;
  hits: CompoundHit[];
  total_hits: number;
}

export async function compoundsSearchCommand(
  smiles: string,
  opts: CompoundsSearchOptions,
): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const limit = parseInt(opts.limit, 10);
  const threshold = parseFloat(opts.threshold);
  const creds = await getAuthCredentials();

  const body = {
    query_smiles: smiles,
    limit,
    score_threshold: threshold,
  };

  const resp = await fetch(`${apiUrl}/search/compounds`, {
    method: "POST",
    headers: {
      ...authHeaders(creds),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    log.error(`Compound search failed: ${await extractApiError(resp)}`);
    process.exit(1);
  }

  const result = (await resp.json()) as CompoundSearchResponse;

  if (opts.json) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  if (!result.hits || result.hits.length === 0) {
    log.info("No compound matches found.");
    return;
  }

  console.log(`\n${pc.bold("Compound Matches")} (${result.total_hits})`);
  console.log("─".repeat(70));

  for (const hit of result.hits) {
    const name = hit.compound_name || hit.canonical_smiles || "(unknown)";
    const doc = hit.artifact_name || hit.artifact_id.slice(0, 8);
    const score = pc.dim(`(${(hit.score * 100).toFixed(0)}%)`);

    console.log(`  ${pc.cyan(truncate(name, 40))} ${score}`);
    console.log(`    ${pc.dim(`in ${doc} p${hit.page_index}`)}`);
    if (hit.canonical_smiles) {
      console.log(`    ${pc.dim(truncate(hit.canonical_smiles, 60))}`);
    }
    console.log("");
  }
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}
