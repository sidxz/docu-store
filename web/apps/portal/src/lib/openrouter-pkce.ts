/**
 * OpenRouter OAuth PKCE, entirely in the browser (tokens live in localStorage,
 * so a Next route handler cannot act as the user).
 *
 * start:    verifier → sessionStorage, redirect to openrouter.ai/auth
 * callback: /onboarding/openrouter?code=… → POST /api/v1/auth/keys → key
 * The key is then PUT to our API (provider=openrouter) and never kept here.
 */
import { deriveCodeChallenge, generateCodeVerifier } from "@duar-auth/js";

const VERIFIER_KEY = "ds-openrouter-verifier";
const RETURN_KEY = "ds-openrouter-return";

export const OPENROUTER_CALLBACK_PATH = "/onboarding/openrouter";

export async function startOpenRouterAuth(returnTo: string): Promise<void> {
  const verifier = generateCodeVerifier();
  const challenge = await deriveCodeChallenge(verifier);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(RETURN_KEY, returnTo);
  const url = new URL("https://openrouter.ai/auth");
  url.searchParams.set("callback_url", `${window.location.origin}${OPENROUTER_CALLBACK_PATH}`);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  window.location.assign(url.toString());
}

/** Where to go after the exchange (read once, then cleared). */
export function takeOpenRouterReturnTo(): string {
  try {
    const v = sessionStorage.getItem(RETURN_KEY) ?? "/";
    sessionStorage.removeItem(RETURN_KEY);
    return v;
  } catch {
    return "/";
  }
}

export async function exchangeOpenRouterCode(code: string): Promise<string> {
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  if (!verifier) throw new Error("OpenRouter sign-in expired — please start again.");
  const res = await fetch("https://openrouter.ai/api/v1/auth/keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, code_verifier: verifier, code_challenge_method: "S256" }),
  });
  if (!res.ok) throw new Error(`OpenRouter key exchange failed (${res.status}).`);
  const { key } = (await res.json()) as { key?: string };
  if (!key) throw new Error("OpenRouter returned no key.");
  return key;
}
