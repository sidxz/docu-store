"use client";

import { useSession } from "@/lib/auth";

export function Topbar() {
  const { user, workspace } = useSession();

  return (
    <header className="flex h-14 items-center justify-between border-b border-gray-200 bg-white px-6">
      {/* Brand */}
      <div className="flex items-center gap-2">
        <span className="text-lg font-semibold text-gray-900">
          DAIKON DocuStore
        </span>
      </div>

      {/* Workspace selector — stub */}
      <div className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600">
        <i className="pi pi-box text-xs" />
        <span>{workspace.name}</span>
        <i className="pi pi-chevron-down text-xs" />
      </div>

      {/* User menu — stub */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-gray-600">{user.name}</span>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-sm font-medium text-blue-700">
          {user.name.charAt(0)}
        </div>
      </div>
    </header>
  );
}
