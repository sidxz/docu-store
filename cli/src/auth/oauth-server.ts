import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { createHash, randomBytes } from "node:crypto";
import open from "open";
import { exchangeCodeForTokens } from "./google.js";

const LOGIN_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
const FIXED_CALLBACK_PORT = 18549;

/** HTML for GitHub flow — extracts id_token from hash fragment and POSTs to local server. */
const HASH_CALLBACK_HTML = `<!DOCTYPE html>
<html><head><title>docu-store login</title>
<style>body{font-family:system-ui,sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#111;color:#eee}p{font-size:1.1rem}</style>
</head><body>
<p id="status">Completing login...</p>
<script>
const hash = window.location.hash.substring(1);
const params = new URLSearchParams(hash);
const token = params.get('id_token');
const nonce = params.get('nonce');
if (token) {
  fetch('/token', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token, nonce: nonce || undefined})
  }).then(r => {
    if (r.ok) {
      document.getElementById('status').textContent = 'Login successful! You can close this tab.';
    } else {
      r.json().then(e => {
        document.getElementById('status').textContent = 'Login failed: ' + (e.error || r.statusText);
      });
    }
  }).catch(() => {
    document.getElementById('status').textContent = 'Login failed. Please try again.';
  });
} else {
  document.getElementById('status').textContent = 'No token received. Please try again.';
}
</script>
</body></html>`;

const SUCCESS_HTML = `<!DOCTYPE html>
<html><head><title>docu-store login</title>
<style>body{font-family:system-ui,sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#111;color:#eee}p{font-size:1.1rem}</style>
</head><body><p>Login successful! You can close this tab.</p></body></html>`;

const ERROR_HTML = (msg: string) => `<!DOCTYPE html>
<html><head><title>docu-store login</title>
<style>body{font-family:system-ui,sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#111;color:#eee}p{font-size:1.1rem;color:#f66}</style>
</head><body><p>Login failed: ${msg}</p></body></html>`;

export interface OAuthResult {
  idpToken: string;
  refreshToken?: string;
  idpExpiresIn?: number; // seconds until IdP token expires
}

/** Generate PKCE code_verifier and code_challenge. */
function generatePKCE(): { codeVerifier: string; codeChallenge: string } {
  const codeVerifier = randomBytes(32).toString("base64url");
  const codeChallenge = createHash("sha256")
    .update(codeVerifier)
    .digest("base64url");
  return { codeVerifier, codeChallenge };
}

/**
 * Start a local HTTP server, open the browser to the IdP login,
 * and wait for the callback with the IdP token.
 *
 * - GitHub: routes through Duar's proxy, token in hash fragment
 * - Google: authorization code + PKCE flow, code in query params
 */
export async function startOAuthFlow(
  duarUrl: string,
  provider: string,
  googleClientId?: string,
  googleClientSecret?: string,
): Promise<OAuthResult> {
  const nonce = randomBytes(16).toString("base64url");
  const pkce = generatePKCE();
  const callbackUrl = `http://localhost:${FIXED_CALLBACK_PORT}/callback`;

  return new Promise<OAuthResult>((resolvePromise, rejectPromise) => {
    let settled = false;

    const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
      if (req.method === "GET" && req.url?.startsWith("/callback")) {
        const url = new URL(req.url, `http://localhost:${FIXED_CALLBACK_PORT}`);
        const code = url.searchParams.get("code");

        if (code && provider === "google" && googleClientId) {
          // Google auth code flow — exchange code for tokens server-side
          try {
            const tokens = await exchangeCodeForTokens(
              code,
              googleClientId,
              googleClientSecret || "",
              callbackUrl,
              pkce.codeVerifier,
            );

            res.writeHead(200, { "Content-Type": "text/html" });
            res.end(SUCCESS_HTML);

            settled = true;
            cleanup();
            resolvePromise({
              idpToken: tokens.id_token,
              refreshToken: tokens.refresh_token,
              idpExpiresIn: tokens.expires_in,
            });
          } catch (err) {
            const msg = err instanceof Error ? err.message : "Unknown error";
            res.writeHead(200, { "Content-Type": "text/html" });
            res.end(ERROR_HTML(msg));
          }
          return;
        }

        // GitHub flow — serve HTML that extracts token from hash fragment
        res.writeHead(200, { "Content-Type": "text/html" });
        res.end(HASH_CALLBACK_HTML);
        return;
      }

      // GitHub flow — receive token POSTed from callback page JS
      if (req.method === "POST" && req.url === "/token") {
        let body = "";
        req.on("data", (chunk: Buffer) => {
          body += chunk.toString();
        });
        req.on("end", () => {
          try {
            const data = JSON.parse(body) as { token?: string; nonce?: string };

            if (data.nonce && data.nonce !== nonce) {
              res.writeHead(400, { "Content-Type": "application/json" });
              res.end(JSON.stringify({ error: "nonce mismatch" }));
              return;
            }

            if (!data.token) {
              res.writeHead(400, { "Content-Type": "application/json" });
              res.end(JSON.stringify({ error: "missing token" }));
              return;
            }

            res.writeHead(200, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ ok: true }));

            settled = true;
            cleanup();
            resolvePromise({ idpToken: data.token });
          } catch {
            res.writeHead(400, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ error: "invalid JSON" }));
          }
        });
        return;
      }

      res.writeHead(404);
      res.end();
    });

    const timeout = setTimeout(() => {
      if (!settled) {
        settled = true;
        cleanup();
        rejectPromise(new Error("Login timed out after 5 minutes"));
      }
    }, LOGIN_TIMEOUT_MS);

    function cleanup() {
      clearTimeout(timeout);
      server.close();
    }

    server.listen(FIXED_CALLBACK_PORT, "127.0.0.1", () => {
      const addr = server.address();
      if (!addr || typeof addr === "string") {
        settled = true;
        cleanup();
        rejectPromise(new Error("Failed to start callback server"));
        return;
      }

      // Build login URL based on provider
      let loginUrl: string;
      try {
        loginUrl = buildLoginUrl(provider, {
          duarUrl,
          callbackUrl,
          nonce,
          googleClientId,
          codeChallenge: pkce.codeChallenge,
        });
      } catch (err) {
        settled = true;
        cleanup();
        rejectPromise(err);
        return;
      }

      console.log(`Opening browser for ${provider} login...`);
      console.log(`If the browser doesn't open, visit:\n  ${loginUrl}\n`);

      open(loginUrl).catch(() => {
        // Browser open failed — user can manually visit the URL
      });
    });
  });
}

function buildLoginUrl(
  provider: string,
  opts: {
    duarUrl: string;
    callbackUrl: string;
    nonce: string;
    googleClientId?: string;
    codeChallenge: string;
  },
): string {
  if (provider === "github") {
    return (
      `${opts.duarUrl.replace(/\/$/, "")}/authz/idp/github/login` +
      `?redirect_uri=${encodeURIComponent(opts.callbackUrl)}&nonce=${opts.nonce}`
    );
  }

  if (provider === "google") {
    if (!opts.googleClientId) {
      throw new Error(
        "Google login requires a client ID. Set it with:\n" +
          "  docu config set google-client-id YOUR_GOOGLE_CLIENT_ID\n" +
          "  or: export DOCU_GOOGLE_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID",
      );
    }
    const params = new URLSearchParams({
      client_id: opts.googleClientId,
      redirect_uri: opts.callbackUrl,
      response_type: "code",
      scope: "openid email profile",
      access_type: "offline",
      prompt: "consent",
      nonce: opts.nonce,
      code_challenge: opts.codeChallenge,
      code_challenge_method: "S256",
    });
    return `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
  }

  throw new Error(
    `Unsupported provider "${provider}". Supported: github, google`,
  );
}
