import { loadConfig } from "../utils/config.js";
import { getAuthCredentials, authHeaders } from "../api/client.js";
import { findArtifactByFilename } from "../utils/artifact-lookup.js";
import { extractApiError } from "../utils/api-error.js";
import * as log from "../utils/logger.js";

interface ReprocessOptions {
  id?: string;
  summarize?: boolean;
  metadata?: boolean;
  all?: boolean;
  apiUrl?: string;
}

interface WorkflowStartedResponse {
  workflow_id: string;
  [key: string]: unknown;
}

export async function reprocessCommand(
  filename: string,
  opts: ReprocessOptions,
): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  const artifactId = opts.id || (await findArtifactByFilename(apiUrl, creds, filename));
  if (!artifactId) {
    log.error(`No artifact found for "${filename}"`);
    process.exit(1);
  }

  const noFlagsSet = !opts.summarize && !opts.metadata && !opts.all;
  const doSummarize = opts.summarize || opts.all || noFlagsSet;
  const doMetadata = opts.metadata || opts.all || noFlagsSet;

  const triggered: string[] = [];

  if (doSummarize) {
    const resp = await fetch(`${apiUrl}/artifacts/${artifactId}/summarize`, {
      method: "POST",
      headers: authHeaders(creds),
    });

    if (resp.ok) {
      const text = await resp.text();
      if (text) {
        const data = JSON.parse(text) as WorkflowStartedResponse;
        log.success(`Summarization started (${data.workflow_id})`);
      } else {
        log.success("Summarization triggered.");
      }
      triggered.push("summarize");
    } else {
      log.error(`Summarization trigger failed: ${await extractApiError(resp)}`);
    }
  }

  if (doMetadata) {
    const resp = await fetch(`${apiUrl}/artifacts/${artifactId}/extract-metadata`, {
      method: "POST",
      headers: authHeaders(creds),
    });

    if (resp.ok) {
      const text = await resp.text();
      if (text) {
        const data = JSON.parse(text) as WorkflowStartedResponse;
        log.success(`Metadata extraction started (${data.workflow_id})`);
      } else {
        log.success("Metadata extraction triggered.");
      }
      triggered.push("metadata");
    } else {
      log.error(`Metadata extraction trigger failed: ${await extractApiError(resp)}`);
    }
  }

  if (triggered.length > 0) {
    log.info(`Track progress: docu status ${opts.id ? `--id ${artifactId}` : filename}`);
  }
}
