import { Library, MessageSquare } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ChatSurface } from "@docu-store/types";

/**
 * How each chat surface presents itself.
 *
 * The two surfaces share ChatPanel, ConversationSidebar, MessageList and the
 * dashboard's recent cards, so their identity has to travel with the data
 * rather than be hardcoded per component — that is how Literature ended up
 * wearing Docu Research's chat bubble, copy and routes in six different
 * places. Defined once here; the sidebar nav, the empty states, the
 * conversation rows, the recent cards and the notification listener all read
 * from it.
 */
export interface SurfaceMeta {
  /** Display name, e.g. sidebar nav label. */
  label: string;
  /** Route segment: `/{workspace}/{segment}[/{conversationId}]`. */
  segment: string;
  icon: LucideIcon;
  iconColor: string;
  /** Copy for a ChatPanel with no conversation selected. */
  emptyTitle: string;
  emptyDescription: string;
  /** Copy for an empty ConversationSidebar list. */
  emptyListText: string;
  /** ChatInput placeholder for this surface. */
  composerPlaceholder: string;
  /** MessageList's in-conversation empty-state prompt. */
  askPrompt: string;
}

export const SURFACES: Record<ChatSurface, SurfaceMeta> = {
  research: {
    label: "Docu Research",
    segment: "chat",
    icon: MessageSquare,
    iconColor: "text-indigo-500",
    emptyTitle: "Start a conversation",
    emptyDescription:
      "Select an existing conversation or start a new one to chat with your documents.",
    emptyListText: "No conversations yet",
    composerPlaceholder: "Ask a question about your documents...",
    askPrompt: "Ask a question about your documents",
  },
  literature: {
    label: "Literature",
    segment: "literature",
    icon: Library,
    iconColor: "text-rose-500",
    emptyTitle: "Find relevant papers",
    emptyDescription:
      "Select an existing search or start a new one to explore published literature.",
    emptyListText: "No searches yet",
    composerPlaceholder: "Search published literature — e.g. inhibitors of Pks13",
    askPrompt: "Search published literature",
  },
};

/** Every route segment a surface can live under — for building route regexes
 *  (e.g. ChatNotifications) without hardcoding the surface list a second time. */
export const SURFACE_SEGMENTS: string[] = Object.values(SURFACES).map((s) => s.segment);

/** `basePath` is the route segment ("chat" | "literature") components are handed. */
export function surfaceFromBasePath(basePath: string | undefined): ChatSurface {
  return basePath === "literature" ? "literature" : "research";
}


/** Builds `/{workspace}/{segment}` or `/{workspace}/{segment}/{conversationId}`. */
export function conversationHref(
  workspace: string,
  surface: ChatSurface,
  conversationId?: string,
): string {
  const base = `/${workspace}/${SURFACES[surface].segment}`;
  return conversationId ? `${base}/${conversationId}` : base;
}
