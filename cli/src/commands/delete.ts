import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";
import { loadConfig } from "../utils/config.js";
import { getAuthCredentials, authHeaders } from "../api/client.js";
import { findArtifactByFilename } from "../utils/artifact-lookup.js";
import * as log from "../utils/logger.js";

interface DeleteOptions {
  id?: string;
  force?: boolean;
  apiUrl?: string;
}

export async function deleteCommand(
  filename: string,
  opts: DeleteOptions,
): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  const artifactId = opts.id || (await findArtifactByFilename(apiUrl, creds, filename));
  if (!artifactId) {
    log.error(`No artifact found for "${filename}"`);
    process.exit(1);
  }

  // Confirm unless --force
  if (!opts.force) {
    const rl = createInterface({ input: stdin, output: stdout });
    try {
      const answer = await rl.question(
        `Delete "${filename}"? This cannot be undone. [y/N]: `,
      );
      if (answer.trim().toLowerCase() !== "y") {
        log.info("Cancelled.");
        return;
      }
    } finally {
      rl.close();
    }
  }

  const resp = await fetch(`${apiUrl}/artifacts/${artifactId}`, {
    method: "DELETE",
    headers: authHeaders(creds),
  });

  if (resp.status === 204 || resp.ok) {
    log.success(`Deleted "${filename}"`);
  } else if (resp.status === 404) {
    log.error("Artifact not found.");
  } else {
    log.error(`Delete failed: ${resp.status}`);
  }
}

