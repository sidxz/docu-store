/**
 * Authz token mint endpoint (BFF).
 *
 * Since Duar 0.11.0 the browser no longer calls Duar's /authz/resolve
 * directly to mint an authz token — that step requires a service key, which must
 * stay server-side. The DuarAuthz client POSTs the IdP token here (same-origin),
 * and this route forwards it to Duar with X-Service-Key. Discovery (workspace
 * listing) still goes browser -> Duar directly; only credential issuance is proxied.
 *
 * Request body (from DuarAuthz.selectWorkspace):
 *   { idp_token, provider, workspace_id, nonce? }
 * Env (server-side, read at request time):
 *   APP_DUAR_URL          — Duar base URL
 *   APP_DUAR_SERVICE_KEY  — a "docu-store" service key (never exposed to the browser)
 */
export async function POST(request: Request) {
  const duarUrl = (process.env.APP_DUAR_URL ?? "http://localhost:9003").replace(/\/+$/, "");
  const serviceKey = process.env.APP_DUAR_SERVICE_KEY;

  if (!serviceKey) {
    return Response.json(
      { detail: "Mint endpoint not configured: APP_DUAR_SERVICE_KEY is missing." },
      { status: 503 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  const upstream = await fetch(`${duarUrl}/authz/resolve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Service-Key": serviceKey,
    },
    body: JSON.stringify(body),
  });

  const data = await upstream.json().catch(() => ({}));
  return Response.json(data, { status: upstream.status });
}
