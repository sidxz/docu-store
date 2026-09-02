"use client";

import { useState } from "react";
import type { SourceCitation } from "@docu-store/types";
import { useChatStore } from "@/lib/stores/chat-store";
import { useConversation } from "@/hooks/use-chat";
import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { SURFACES } from "@/lib/surfaces";
import { LiteraturePanel } from "./LiteraturePanel";

/**
 * Docu Research's layout with the right-hand panel swapped: papers instead of
 * corpus sources. Everything down the middle is reused unchanged, and the mode
 * is pinned here rather than read from the store so that asking a question in
 * this surface cannot change the mode selected for Docu Research.
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

  // The live list only speaks for the conversation being streamed. Reopening a
  // past conversation has no stream to fill it, so fall back to what the last
  // answered turn was persisted with — otherwise its citations lead to an empty
  // panel, which is the same as leading nowhere.
  const live = useChatStore((s) => s.literatureResults);
  const liveFinal = useChatStore((s) => s.finalSources);
  const liveStreaming = useChatStore((s) => s.streamingSources);
  const streamingConversationId = useChatStore((s) => s.streamingConversationId);
  const { data } = useConversation(conversationId);

  const streamingHere = !!conversationId && streamingConversationId === conversationId;
  let results = streamingHere ? live : [];
  // Papers and citations must come from the *same* turn, or the green tint
  // marks the wrong cards and [n] scrolls to the wrong paper.
  let sources: SourceCitation[] = streamingHere ? (liveFinal ?? liveStreaming) : [];

  if (!streamingHere) {
    const messages = data?.messages ?? [];
    for (let i = messages.length - 1; i >= 0; i--) {
      const message = messages[i];
      if (message.role === "assistant" && message.literature_results?.length) {
        results = message.literature_results;
        sources = message.sources ?? [];
        break;
      }
    }
    // A turn that has just finished streaming is in the store but not yet
    // refetched; prefer the live pair over an empty fallback.
    if (results.length === 0) {
      results = live;
      sources = liveFinal ?? liveStreaming;
    }
  }

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
            basePath={SURFACES.literature.segment}
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
          basePath={SURFACES.literature.segment}
          placeholder={SURFACES.literature.composerPlaceholder}
        />
      </div>

      <div
        className={`flex-shrink-0 overflow-hidden border-l border-border-default bg-surface transition-all duration-300 ease-in-out ${
          showPanel ? "w-96 opacity-100" : "w-0 border-l-0 opacity-0"
        }`}
      >
        <div className="h-full w-96">
          {results.length > 0 && (
            <LiteraturePanel
              results={results}
              sources={sources}
              onClose={() => setPanelOpen(false)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
