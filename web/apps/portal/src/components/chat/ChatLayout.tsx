"use client";

import { useState } from "react";
import { useChatStore } from "@/lib/stores/chat-store";
import { ConversationSidebar } from "./ConversationSidebar";
import { ChatPanel } from "./ChatPanel";
import { SourcesPanel } from "./SourcesPanel";
import type { SourceCitation } from "@docu-store/types";

interface ChatLayoutProps {
  workspace: string;
  conversationId?: string;
}

export function ChatLayout({ workspace, conversationId }: ChatLayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(true);
  // Track the "active" sources to display — set by ChatPanel when sources arrive
  const [activeSources, setActiveSources] = useState<SourceCitation[]>([]);

  const hasSources = activeSources.length > 0;

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: Conversation sidebar */}
      <div
        className={`border-r border-surface-200 dark:border-surface-700 transition-all duration-200 flex-shrink-0 ${
          sidebarCollapsed ? "w-0 overflow-hidden" : "w-72"
        }`}
      >
        <ConversationSidebar
          workspace={workspace}
          activeConversationId={conversationId}
          onCollapse={() => setSidebarCollapsed(true)}
        />
      </div>

      {/* Center: Chat panel */}
      <div className="flex-1 flex flex-col min-w-0">
        <ChatPanel
          workspace={workspace}
          conversationId={conversationId}
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
          onSourcesChange={setActiveSources}
          sourcesOpen={sourcesOpen && hasSources}
          onToggleSources={() => setSourcesOpen(!sourcesOpen)}
        />
      </div>

      {/* Right: Sources panel */}
      {hasSources && sourcesOpen && (
        <div className="w-80 border-l border-surface-200 dark:border-surface-700 flex-shrink-0 bg-surface-0 dark:bg-surface-900">
          <SourcesPanel
            sources={activeSources}
            workspace={workspace}
            onClose={() => setSourcesOpen(false)}
          />
        </div>
      )}
    </div>
  );
}
