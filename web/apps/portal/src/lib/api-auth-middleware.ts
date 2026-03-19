import type { Middleware } from "openapi-fetch";
import { getAuthzClient } from "./authz-client";

export const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const client = getAuthzClient();
    const headers = client.getHeaders();
    for (const [key, value] of Object.entries(headers)) {
      request.headers.set(key, value);
    }
    return request;
  },
  async onResponse({ response, request }) {
    if (response.status === 401) {
      const client = getAuthzClient();
      const refreshed = await client.refresh();
      if (refreshed) {
        // Retry the original request with fresh tokens
        const headers = client.getHeaders();
        const retryInit: RequestInit = {
          method: request.method,
          headers: new Headers(request.headers),
          body: request.bodyUsed ? undefined : await request.clone().text() || undefined,
        };
        for (const [key, value] of Object.entries(headers)) {
          (retryInit.headers as Headers).set(key, value);
        }
        return fetch(request.url, retryInit);
      }
    }
    return response;
  },
};
