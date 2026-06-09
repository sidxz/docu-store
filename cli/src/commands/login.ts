import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";
import { loadConfig } from "../utils/config.js";
import { saveCredentials, type Credentials } from "../auth/credentials.js";
import { startOAuthFlow } from "../auth/oauth-server.js";
import { mint, resolve, type SentinelWorkspace } from "../auth/sentinel.js";
import * as log from "../utils/logger.js";

interface LoginOptions {
  provider: string;
  workspace?: string;
  token?: string;
  sentinelUrl?: string;
}

export async function loginCommand(opts: LoginOptions): Promise<void> {
  const config = loadConfig();
  const sentinelUrl = opts.sentinelUrl || config.sentinel_url;

  // Token paste fallback (headless/SSH environments)
  if (opts.token) {
    await tokenLogin(opts.token, opts.workspace, sentinelUrl, opts.provider);
    return;
  }

  // Browser OAuth flow
  const oauthResult = await startOAuthFlow(
    sentinelUrl,
    opts.provider,
    config.google_client_id,
    config.google_client_secret,
  );
  const { idpToken } = oauthResult;
  log.success("IdP token received");

  // Step 1: Resolve without workspace to get user + workspace list
  log.info("Authenticating with Sentinel...");
  const initial = await resolve(sentinelUrl, idpToken, opts.provider);

  if (!initial.workspaces || initial.workspaces.length === 0) {
    log.error("No workspaces available for this account.");
    process.exit(1);
  }

  // Step 2: Select workspace
  let selectedWorkspace: SentinelWorkspace;

  if (opts.workspace) {
    // Match by slug or ID
    const match = initial.workspaces.find(
      (w) => w.slug === opts.workspace || w.id === opts.workspace,
    );
    if (!match) {
      log.error(`Workspace "${opts.workspace}" not found. Available:`);
      for (const w of initial.workspaces) {
        console.log(`  - ${w.slug} (${w.id})`);
      }
      process.exit(1);
    }
    selectedWorkspace = match;
  } else if (initial.workspaces.length === 1) {
    selectedWorkspace = initial.workspaces[0];
  } else {
    selectedWorkspace = await promptWorkspaceSelection(initial.workspaces);
  }

  // Step 3: Mint the authz token via the backend (service key stays server-side)
  const result = await mint(
    config.api_url,
    idpToken,
    opts.provider,
    selectedWorkspace.id,
  );

  if (!result.authz_token || !result.expires_in) {
    log.error("Failed to obtain authorization token.");
    process.exit(1);
  }

  const creds: Credentials = {
    idp_token: idpToken,
    authz_token: result.authz_token,
    provider: opts.provider,
    workspace_id: selectedWorkspace.id,
    workspace_slug: selectedWorkspace.slug,
    user_email: result.user.email,
    user_name: result.user.name,
    expires_at: Date.now() / 1000 + result.expires_in,
    refresh_token: oauthResult.refreshToken,
    idp_token_expires_at: oauthResult.idpExpiresIn
      ? Date.now() / 1000 + oauthResult.idpExpiresIn
      : undefined,
    google_client_id: opts.provider === "google" ? config.google_client_id : undefined,
    google_client_secret: opts.provider === "google" ? config.google_client_secret : undefined,
  };

  saveCredentials(creds);
  log.success(
    `Logged in as ${result.user.email} (workspace: ${selectedWorkspace.slug})`,
  );
}

async function tokenLogin(
  token: string,
  workspace: string | undefined,
  sentinelUrl: string,
  provider: string,
): Promise<void> {
  if (!workspace) {
    log.error("--workspace is required when using --token");
    process.exit(1);
  }

  const creds: Credentials = {
    idp_token: "",
    authz_token: token,
    provider,
    workspace_id: workspace,
    workspace_slug: null,
    user_email: null,
    user_name: null,
    expires_at: Date.now() / 1000 + 300, // assume 5 min
  };

  saveCredentials(creds);
  log.success("Token saved.");
  log.warn(
    "Auto-refresh is not available with manual tokens. " +
      "When expired, run: docu login",
  );
}

async function promptWorkspaceSelection(
  workspaces: SentinelWorkspace[],
): Promise<SentinelWorkspace> {
  console.log("\nAvailable workspaces:");
  for (let i = 0; i < workspaces.length; i++) {
    console.log(`  ${i + 1}. ${workspaces[i].slug} (${workspaces[i].role})`);
  }

  const rl = createInterface({ input: stdin, output: stdout });
  try {
    const answer = await rl.question("\nSelect workspace [1]: ");
    const idx = answer.trim() ? parseInt(answer.trim(), 10) - 1 : 0;

    if (isNaN(idx) || idx < 0 || idx >= workspaces.length) {
      log.error("Invalid selection.");
      process.exit(1);
    }
    return workspaces[idx];
  } finally {
    rl.close();
  }
}
