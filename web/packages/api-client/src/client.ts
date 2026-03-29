/**
 * Typed HTTP client for the DocuStore FastAPI backend.
 *
 * `paths` is the auto-generated type map produced by openapi-typescript from
 * the FastAPI OpenAPI spec (see scripts/generate.ts). Running `pnpm generate`
 * in the workspace root regenerates schema.d.ts.
 *
 * All GET/POST/DELETE calls through this client are fully type-safe: path
 * params, query params, request bodies, and response shapes are all inferred.
 */
import createClient from "openapi-fetch";
import type { paths } from "./schema";

/** Mutable singleton — reconfigured once at app init via `setApiBaseUrl`. */
export let apiClient = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
});

/** Recreate the API client with a new base URL (called once during app init). */
export function setApiBaseUrl(url: string) {
  apiClient = createClient<paths>({ baseUrl: url });
}
