import {
  SentinelAuthz,
  AuthzLocalStorageStore,
  IdpConfigs,
} from "@sentinel-auth/js";
import type { IdpConfig } from "@sentinel-auth/js";
import type { AppConfig } from "./app-config";

/** Lazy singleton — avoids localStorage access during SSR/prerendering. */
let _client: SentinelAuthz | null = null;

/**
 * Create (or return cached) SentinelAuthz client.
 * Accepts runtime config so no process.env is read at module load.
 */
export function getAuthzClient(config?: AppConfig): SentinelAuthz {
  if (!_client) {
    const sentinelUrl =
      config?.sentinelUrl ||
      process.env.NEXT_PUBLIC_SENTINEL_URL ||
      "http://localhost:9003";
    const googleClientId =
      config?.googleClientId ||
      process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ||
      "";
    const githubClientId =
      config?.githubClientId ||
      process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID ||
      "";

    const githubIdpConfig: IdpConfig = {
      clientId: githubClientId,
      authorizationUrl: `${sentinelUrl}/authz/idp/github/login`,
      scopes: ["read:user", "user:email"],
      responseType: "code",
    };

    _client = new SentinelAuthz({
      sentinelUrl,
      storage: new AuthzLocalStorageStore(),
      idps: {
        google: IdpConfigs.google(googleClientId),
        github: githubIdpConfig,
      },
    });
  }
  return _client;
}
