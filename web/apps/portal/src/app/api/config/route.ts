/**
 * Runtime configuration endpoint.
 *
 * Reads environment variables at request time (NOT build time), enabling
 * a single universal Docker image that works across environments.
 *
 * Variables use APP_ prefix (server-side only) instead of NEXT_PUBLIC_
 * (which gets baked into the JS bundle at build time).
 */
export function GET() {
  return Response.json({
    apiUrl: process.env.APP_API_URL ?? "http://localhost:8000",
    appUrl: process.env.APP_URL ?? "http://localhost:15000",
    sentinelUrl: process.env.APP_SENTINEL_URL ?? "http://localhost:9003",
    googleClientId: process.env.APP_GOOGLE_CLIENT_ID ?? "",
    githubClientId: process.env.APP_GITHUB_CLIENT_ID ?? "",
    entraIdClientId: process.env.APP_ENTRA_ID_CLIENT_ID ?? "",
    umamiUrl: process.env.APP_UMAMI_URL ?? "",
    umamiWebsiteId: process.env.APP_UMAMI_WEBSITE_ID ?? "",
  });
}
