/**
 * Whether AuthzProvider's silent (prompt=none) re-auth should run for a route.
 *
 * Must NOT run on the auth-flow routes: on `/auth/callback` it would preempt the
 * OAuth response the callback exists to process, and on `/login` it would hijack
 * an interactive sign-in.
 *
 * ponytail: verbatim copy of prot-cellar's proven helper; no test since the
 * portal has no test runner and this is a two-line prefix check.
 */
const AUTH_FLOW_PREFIXES = ["/login", "/auth"];

export function shouldAutoReauth(pathname: string | null): boolean {
  if (!pathname) return false;
  return !AUTH_FLOW_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}
