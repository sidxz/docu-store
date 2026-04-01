import { writeFileSync } from "node:fs";
import { join, resolve as resolvePath } from "node:path";
import { loadConfig } from "../utils/config.js";
import { getAuthCredentials, authHeaders } from "../api/client.js";
import { findArtifactByFilename } from "../utils/artifact-lookup.js";
import * as log from "../utils/logger.js";

interface ExportOptions {
  id?: string;
  out?: string;
  apiUrl?: string;
}

export async function exportCommand(
  filename: string,
  opts: ExportOptions,
): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  const artifactId = opts.id || (await findArtifactByFilename(apiUrl, creds, filename));
  if (!artifactId) {
    log.error(`No artifact found for "${filename}"`);
    process.exit(1);
  }

  // Get artifact details for the storage location and filename
  const detailResp = await fetch(`${apiUrl}/artifacts/${artifactId}`, {
    headers: authHeaders(creds),
  });

  if (!detailResp.ok) {
    log.error(`Failed to get artifact details: ${detailResp.status}`);
    process.exit(1);
  }

  const detail = (await detailResp.json()) as {
    artifact_id: string;
    source_filename: string | null;
    storage_location: string;
  };

  // Download the blob
  const blobUrl = `${apiUrl}/artifacts/${artifactId}/blob`;
  log.info(`Downloading ${detail.source_filename || artifactId}...`);

  const blobResp = await fetch(blobUrl, {
    headers: authHeaders(creds),
  });

  if (!blobResp.ok) {
    log.error(`Download failed: ${blobResp.status}`);
    process.exit(1);
  }

  const buffer = Buffer.from(await blobResp.arrayBuffer());
  const outFilename = detail.source_filename || `${artifactId}.pdf`;
  const outDir = opts.out ? resolvePath(opts.out) : process.cwd();
  const outPath = join(outDir, outFilename);

  writeFileSync(outPath, buffer);
  log.success(`Saved to ${outPath} (${(buffer.length / 1024 / 1024).toFixed(1)} MB)`);
}

