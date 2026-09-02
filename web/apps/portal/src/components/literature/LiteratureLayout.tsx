"use client";

import { useState } from "react";
import { useChatStore } from "@/lib/stores/chat-store";
import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { LiteraturePanel } from "./LiteraturePanel";

/**
 * Deep Research's layout with the right-hand panel swapped: papers instead of
 * corpus sources. Everything down the middle is reused unchanged, and the mode
 * is pinned here rather than read from the store so that asking a question in
 * this surface cannot change the mode selected for Deep Research.
 */
export function LiteratureLayout({
  workspace,
  conversationId,
}: {
  workspace: string;
  conversationId?: string;
}) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const results = useChatStore((s) => s.literatureResults);

  const showPanel = results.length > 0 && panelOpen;

  return (
    <div className="flex h-full overflow-hidden">
      <div
        className={`flex-shrink-0 overflow-hidden border-r border-border-default transition-all duration-300 ease-in-out ${
          sidebarCollapsed ? "w-0" : "w-72"
        }`}
      >
        <div className="h-full w-72">
          <ConversationSidebar
            workspace={workspace}
            activeConversationId={conversationId}
            onCollapse={() => setSidebarCollapsed(true)}
            basePath="literature"
          />
        </div>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <ChatPanel
          workspace={workspace}
          conversationId={conversationId}
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
          onSourcesChange={() => {}}
          sourcesOpen={showPanel}
          onToggleSources={() => setPanelOpen(!panelOpen)}
          forceMode="literature"
          basePath="literature"
          placeholder="Search published literature — e.g. inhibitors of Pks13"
        />
      </div>

      <div
        className={`flex-shrink-0 overflow-hidden border-l border-border-default bg-surface transition-all duration-300 ease-in-out ${
          showPanel ? "w-96 opacity-100" : "w-0 border-l-0 opacity-0"
        }`}
      >
        <div className="h-full w-96">
          {results.length > 0 && (
            <LiteraturePanel results={results} onClose={() => setPanelOpen(false)} />
          )}
        </div>
      </div>
    </div>
  );
}
