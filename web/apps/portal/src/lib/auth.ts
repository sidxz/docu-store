/**
 * Auth — backed by Duar AuthZ SDK.
 *
 * Provides a `useSession()` hook with the same interface components already consume.
 */

import { useAuthz } from "@duar-auth/react";
import type { User, Workspace } from "@docu-store/types";

interface Session {
  user: User;
  workspace: Workspace;
  isAuthenticated: boolean;
  isLoading: boolean;
}

const EMPTY_USER: User = {
  id: "",
  name: "",
  email: "",
  avatar_url: null,
};

const EMPTY_WORKSPACE: Workspace = {
  id: "",
  slug: "",
  name: "",
};

export function useSession(): Session {
  const { user, isAuthenticated, isLoading } = useAuthz();

  if (!user) {
    return {
      user: EMPTY_USER,
      workspace: EMPTY_WORKSPACE,
      isAuthenticated: false,
      isLoading,
    };
  }

  return {
    user: {
      id: user.userId,
      name: user.name,
      email: user.email,
      avatar_url: null,
    },
    workspace: {
      id: user.workspaceId,
      slug: user.workspaceSlug,
      // SDK JWT doesn't carry workspace name — slug is the best available
      name: user.workspaceSlug,
    },
    isAuthenticated,
    isLoading,
  };
}
