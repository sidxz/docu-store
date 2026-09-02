import { Library, MessageSquare } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ChatSurface } from "@docu-store/types";

/**
 * How each chat surface presents itself.
 *
 * The two surfaces share ChatPanel, ConversationSidebar and the dashboard's
 * recent cards, so their identity has to travel with the data rather than be
 * hardcoded per component — that is how Literature ended up wearing Deep
 * Research's chat bubble in four different places. Defined once here; the
 * sidebar nav, the empty states, the conversation rows and the recent cards
 * all read from it.
 */
export const SURFACE_ICON: Record<ChatSurface, LucideIcon> = {
  research: MessageSquare,
  literature: Library,
};

export const SURFACE_ICON_COLOR: Record<ChatSurface, string> = {
  research: "text-indigo-500",
  literature: "text-rose-500",
};

/** `basePath` is the route segment ("chat" | "literature") components are handed. */
export function surfaceFromBasePath(basePath: string | undefined): ChatSurface {
  return basePath === "literature" ? "literature" : "research";
}
