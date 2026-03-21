"use client";

import { useState } from "react";
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
  const [activeSources, setActiveSources] = useState<SourceCitation[]>([]);

  const hasSources = activeSources.length > 0;
  const showSources = hasSources && sourcesOpen;

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: Conversation sidebar */}
      <div
        className={`border-r border-border-default transition-all duration-300 ease-in-out flex-shrink-0 overflow-hidden ${
          sidebarCollapsed ? "w-0" : "w-72"
        }`}
      >
        <div className="w-72 h-full">
          <ConversationSidebar
            workspace={workspace}
            activeConversationId={conversationId}
            onCollapse={() => setSidebarCollapsed(true)}
          />
        </div>
      </div>

      {/* Center: Chat panel */}
      <div className="flex-1 flex flex-col min-w-0">
        <ChatPanel
          workspace={workspace}
          conversationId={conversationId}
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
          onSourcesChange={setActiveSources}
          sourcesOpen={showSources}
          onToggleSources={() => setSourcesOpen(!sourcesOpen)}
        />
      </div>

      {/* Right: Sources panel — always rendered, animated via width */}
      <div
        className={`border-l border-border-default flex-shrink-0 bg-surface transition-all duration-300 ease-in-out overflow-hidden ${
          showSources ? "w-80 opacity-100" : "w-0 opacity-0 border-l-0"
        }`}
      >
        <div className="w-80 h-full">
          {hasSources && (
            <SourcesPanel
              sources={activeSources}
              workspace={workspace}
              onClose={() => setSourcesOpen(false)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
