/**
 * Auth stub — library-agnostic.
 *
 * Returns mock session data. No real auth dependency.
 * Will be replaced with Better Auth or Auth.js in Phase 6.
 */

import type { User, Workspace } from "@docu-store/types";

interface Session {
  user: User;
  workspace: Workspace;
  isAuthenticated: boolean;
}

const STUB_SESSION: Session = {
  user: {
    id: "stub-user-id",
    name: "Developer",
    email: "dev@localhost",
    avatar_url: null,
  },
  workspace: {
    id: "default",
    slug: "default",
    name: "Default Workspace",
  },
  isAuthenticated: true,
};

export function useSession(): Session {
  return STUB_SESSION;
}
