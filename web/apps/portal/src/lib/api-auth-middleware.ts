import type { Middleware } from "openapi-fetch";
import { getAuthzClient } from "./authz-client";

// Store request bodies before they're consumed by fetch, so 401 retries
// can resend the original body.
//
// Safety note: the backend rejects 401 at the auth middleware layer, before
// the request handler processes any mutations. Replaying the original request
// after a token refresh is therefore safe for all HTTP methods — the first
// attempt never reached the handler.
const savedBodies = new WeakMap<Request, string | null>();

// Track whether a request has already been retried to prevent infinite loops
const retriedRequests = new WeakSet<Request>();

export const authMiddleware: Middleware = {
  async onRequest({ request }) {
    // Clone and read the body now — it will be consumed once the request is sent.
    const clone = request.clone();
    const text = await clone.text();
    savedBodies.set(request, text || null);

    const client = getAuthzClient();
    const headers = client.getHeaders();
    for (const [key, value] of Object.entries(headers)) {
      request.headers.set(key, value);
    }
    return request;
  },
  async onResponse({ response, request }) {
    if (response.status === 401 && !retriedRequests.has(request)) {
      retriedRequests.add(request);
      const client = getAuthzClient();
      const refreshed = await client.refresh();
      if (refreshed) {
        const headers = client.getHeaders();
        const retryInit: RequestInit = {
          method: request.method,
          headers: new Headers(request.headers),
          body: savedBodies.get(request) ?? undefined,
        };
        for (const [key, value] of Object.entries(headers)) {
          (retryInit.headers as Headers).set(key, value);
        }
        savedBodies.delete(request);
        return fetch(request.url, retryInit);
      }
    }
    savedBodies.delete(request);
    return response;
  },
};
