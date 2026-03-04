import type { ReactNode } from "react";

import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";

export default async function WorkspaceLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ workspace: string }>;
}) {
  const { workspace } = await params;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar workspaceSlug={workspace} />
      <div className="flex flex-1 flex-col overflow-hidden transition-[margin] duration-200">
        <Topbar />
        <main className="flex-1 overflow-y-auto bg-surface-sunken p-6 transition-colors duration-200 page-enter">
          {children}
        </main>
      </div>
    </div>
  );
}
