import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Proxy stub — passes all requests through.
 *
 * Phase 6 will add:
 *   - Auth check (redirect unauthenticated users to /login)
 *   - Workspace membership validation
 *   - Token refresh
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Extract workspace slug from path (first segment after /)
  const segments = pathname.split("/").filter(Boolean);
  const workspaceSlug = segments[0];

  if (workspaceSlug && workspaceSlug !== "(auth)") {
    // Future: validate workspace membership here
    const response = NextResponse.next();
    response.headers.set("x-workspace-slug", workspaceSlug);
    return response;
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next|api|favicon\\.ico|.*\\..*).*)"],
};
