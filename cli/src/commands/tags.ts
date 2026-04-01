import { loadConfig } from "../utils/config.js";
import { getAuthCredentials, authHeaders } from "../api/client.js";
import { extractApiError } from "../utils/api-error.js";
import * as log from "../utils/logger.js";
import pc from "picocolors";

interface TagsOptions {
  limit: string;
  json?: boolean;
  apiUrl?: string;
}

// ── Popular tags ─────────────────────────────────────────────────────

interface PopularTag {
  tag_value?: string;
  entity_type?: string;
  count?: number;
  [key: string]: unknown;
}

export async function tagsPopularCommand(opts: TagsOptions): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const limit = parseInt(opts.limit, 10);
  const creds = await getAuthCredentials();

  const params = new URLSearchParams({ limit: String(limit) });
  const resp = await fetch(`${apiUrl}/browse/tags/popular?${params}`, {
    headers: authHeaders(creds),
  });

  if (!resp.ok) {
    log.error(`Failed: ${await extractApiError(resp)}`);
    process.exit(1);
  }

  const tags = (await resp.json()) as PopularTag[];

  if (opts.json) {
    console.log(JSON.stringify(tags, null, 2));
    return;
  }

  if (!tags.length) {
    log.info("No tags found.");
    return;
  }

  console.log(`\n${pc.bold("Popular Tags")}`);
  console.log("─".repeat(50));

  for (const t of tags) {
    const value = t.tag_value || t.entity_type || "(unknown)";
    const count = t.count != null ? pc.dim(`(${t.count})`) : "";
    const type = t.entity_type ? pc.dim(`[${t.entity_type}]`) : "";
    console.log(`  ${value.padEnd(30)} ${type} ${count}`);
  }
  console.log("");
}

// ── Suggest tags ─────────────────────────────────────────────────────

export async function tagsSuggestCommand(
  query: string,
  opts: TagsOptions,
): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const limit = parseInt(opts.limit, 10);
  const creds = await getAuthCredentials();

  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const resp = await fetch(`${apiUrl}/browse/tags/suggest?${params}`, {
    headers: authHeaders(creds),
  });

  if (!resp.ok) {
    log.error(`Failed: ${await extractApiError(resp)}`);
    process.exit(1);
  }

  const suggestions = (await resp.json()) as Array<Record<string, string>>;

  if (opts.json) {
    console.log(JSON.stringify(suggestions, null, 2));
    return;
  }

  if (!suggestions.length) {
    log.info(`No suggestions for "${query}".`);
    return;
  }

  console.log(`\n${pc.bold("Tag Suggestions")} for "${query}"`);
  console.log("─".repeat(50));

  for (const s of suggestions) {
    const value = s.tag_value || s.value || Object.values(s)[0] || "";
    const type = s.entity_type ? pc.dim(`[${s.entity_type}]`) : "";
    console.log(`  ${value.padEnd(30)} ${type}`);
  }
  console.log("");
}

// ── Categories ───────────────────────────────────────────────────────

interface TagCategory {
  entity_type: string;
  display_name: string;
  artifact_count: number;
  distinct_count: number;
}

interface CategoriesResponse {
  categories: TagCategory[];
  total_artifacts: number;
}

export async function tagsCategoriesCommand(opts: TagsOptions): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  const resp = await fetch(`${apiUrl}/browse/categories`, {
    headers: authHeaders(creds),
  });

  if (!resp.ok) {
    log.error(`Failed: ${await extractApiError(resp)}`);
    process.exit(1);
  }

  const data = (await resp.json()) as CategoriesResponse;

  if (opts.json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  console.log(`\n${pc.bold("Tag Categories")} (${data.total_artifacts} artifacts)`);
  console.log("─".repeat(60));

  const header =
    "Category".padEnd(20) +
    "Artifacts".padEnd(12) +
    "Unique Tags";
  console.log(`  ${header}`);
  console.log(`  ${"─".repeat(50)}`);

  for (const c of data.categories) {
    console.log(
      `  ${c.display_name.padEnd(20)}${String(c.artifact_count).padEnd(12)}${c.distinct_count}`,
    );
  }
  console.log("");
}
