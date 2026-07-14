import { getAuthzClient } from "./authz-client";
import { API_URL } from "./constants";
import { ApiError } from "./api-error";

/**
 * Fetch wrapper that injects Sentinel auth headers and retries on 401.
 * Use this for API calls that can't go through the openapi-fetch `apiClient`
 * (e.g. endpoints not in the OpenAPI spec, or browse/dashboard/plugin endpoints).
 */
export async function authFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const client = getAuthzClient();
  const headers = new Headers(init?.headers);
  for (const [key, value] of Object.entries(client.getHeaders())) {
    headers.set(key, value);
  }

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });

  if (res.status === 401) {
    const refreshed = await client.refresh();
    if (refreshed) {
      const retryHeaders = new Headers(init?.headers);
      for (const [key, value] of Object.entries(client.getHeaders())) {
        retryHeaders.set(key, value);
      }
      return fetch(`${API_URL}${path}`, { ...init, headers: retryHeaders });
    }
  }

  return res;
}

/**
 * Extract FastAPI's error `detail` from a non-OK response body.
 * Re-throws AbortError (navigation mid-read must stay an abort); any other
 * parse failure (non-JSON body) resolves to undefined.
 */
export async function readErrorDetail(res: Response): Promise<string | undefined> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return typeof body?.detail === "string" ? body.detail : undefined;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    return undefined;
  }
}

/**
 * Convenience: authFetch + JSON parse. Throws ApiError on non-OK responses.
 * 204/empty responses resolve to undefined.
 */
export async function authFetchJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await authFetch(path, init);
  if (!res.ok) {
    const detail = await readErrorDetail(res);
    throw new ApiError(detail ?? `API error: ${res.statusText}`, res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
