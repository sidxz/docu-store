import {
  DuarAuthz,
  AuthzLocalStorageStore,
  IdpConfigs,
} from "@duar-auth/js";
import type { IdpConfig } from "@duar-auth/js";
import type { AppConfig } from "./app-config";
import { appPath } from "./base-path";

/** Lazy singleton — avoids localStorage access during SSR/prerendering. */
let _client: DuarAuthz | null = null;

/**
 * Create (or return cached) DuarAuthz client.
 * Accepts runtime config so no process.env is read at module load.
 */
export function getAuthzClient(config?: AppConfig): DuarAuthz {
  if (!_client) {
    const duarUrl =
      config?.duarUrl ||
      process.env.NEXT_PUBLIC_DUAR_URL ||
      "http://localhost:9003";
    const googleClientId =
      config?.googleClientId ||
      process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ||
      "";
    const githubClientId =
      config?.githubClientId ||
      process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID ||
      "";
    const entraIdClientId = config?.entraIdClientId || process.env.NEXT_PUBLIC_ENTRA_ID_CLIENT_ID || "";
    const entraIdTenantId = config?.entraIdTenantId || process.env.NEXT_PUBLIC_ENTRA_ID_TENANT_ID || "";
    if (Boolean(entraIdClientId) !== Boolean(entraIdTenantId)) {
      throw new Error("Entra login requires both client ID and tenant ID.");
    }

    const githubIdpConfig: IdpConfig = {
      clientId: githubClientId,
      authorizationUrl: `${duarUrl}/authz/idp/github/login`,
      scopes: ["read:user", "user:email"],
      responseType: "code",
    };

    _client = new DuarAuthz({
      duarUrl,
      // Required since Duar 0.11.0: the browser no longer mints authz tokens
      // directly. It POSTs to this same-origin route, which forwards to Duar's
      // /authz/resolve with the service key. See app/api/auth/mint/route.ts.
      mintEndpoint: appPath("/api/auth/mint"),
      redirectUri: `${window.location.origin}${appPath("/auth/callback")}`,
      storage: new AuthzLocalStorageStore(),
      // Refresh the authz token shortly before it expires so an active session
      // never lapses. (Defaults are true/30 in 0.13.x; set explicitly on this
      // auth boundary. The reload bounce is fixed by autoReauth in Providers,
      // not this — see AuthState 'needs_reauth'.)
      autoRefresh: true,
      refreshBuffer: 30,
      idps: {
        google: IdpConfigs.google(googleClientId),
        github: githubIdpConfig,
        ...(entraIdClientId && entraIdTenantId
          ? { entra_id: IdpConfigs.entraId(entraIdClientId, entraIdTenantId) }
          : {}),
      },
    });
  }
  return _client;
}
