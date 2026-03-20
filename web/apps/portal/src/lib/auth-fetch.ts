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
 * Convenience: authFetch + JSON parse. Throws on non-OK responses.
 */
export async function authFetchJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await authFetch(path, init);
  if (!res.ok) throw new ApiError(`API error: ${res.statusText}`, res.status);
  return res.json();
}
