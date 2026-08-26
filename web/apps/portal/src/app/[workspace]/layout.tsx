import type { ReactNode } from "react";

import { LlmProviderBanner } from "@/components/layout/LlmProviderBanner";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { AuthGuardWrapper } from "@/components/providers/AuthGuardWrapper";
import { AnalyticsProvider } from "@/components/providers/AnalyticsProvider";
import { ChatNotifications } from "@/components/chat/ChatNotifications";

/**
 * Persistent shell for all workspace routes: /[workspace]/**
 *
 * Renders a fixed-height viewport split into Sidebar (left) and
 * a scrollable main content area (right).
 *
 * AuthGuardWrapper redirects unauthenticated users to /login.
 *
 * Note: `params` is a Promise in Next.js 16 — always await before accessing.
 */
export default async function WorkspaceLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ workspace: string }>;
}) {
  const { workspace } = await params;

  return (
    <AuthGuardWrapper>
      <AnalyticsProvider />
      <ChatNotifications />
      <div className="flex h-screen overflow-hidden">
        <Sidebar workspaceSlug={workspace} />
        <div className="flex flex-1 flex-col overflow-hidden transition-[margin] duration-200">
          <Topbar />
          <LlmProviderBanner />
          <main className="flex-1 overflow-y-auto bg-surface-sunken p-6 transition-colors duration-200 page-enter">
            {children}
          </main>
        </div>
      </div>
    </AuthGuardWrapper>
  );
}
