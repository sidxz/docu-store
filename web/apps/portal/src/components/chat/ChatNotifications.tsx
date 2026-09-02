"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";
import { useChatStore } from "@/lib/stores/chat-store";
import { SURFACES, SURFACE_SEGMENTS } from "@/lib/surfaces";

const CONVERSATION_ROUTE = new RegExp(`/(?:${SURFACE_SEGMENTS.join("|")})/([0-9a-f-]{36})`);

const DISMISS_KEY = "chat-notify-dismissed";
const PROMPT_AFTER_MS = 12_000;

/**
 * Null-rendering listener mounted in the workspace layout (it must outlive
 * the chat routes). Three jobs:
 * 1. When a stream drags past ~12s, offer browser notifications once.
 * 2. When an answer completes while the user is elsewhere, signal it:
 *    sticky in-app toast + unread dot when they're off the conversation
 *    route, plus a native Notification only when the tab is hidden (the
 *    one case a toast can't reach — and OS banners can be suppressed by
 *    the system, so they're never the sole channel for a visible tab).
 * 3. Landing on a conversation consumes its signals (toast + unread dot).
 */
export function ChatNotifications() {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const router = useRouter();
  const pathname = usePathname();
  const pathnameRef = useRef(pathname);
  pathnameRef.current = pathname;

  // Consume "answer ready" signals for the conversation being viewed,
  // however the user got there (toast View button, sidebar, reload).
  useEffect(() => {
    const convId = pathname?.match(CONVERSATION_ROUTE)?.[1];
    if (convId) {
      toast.dismiss(`chat-ready-${convId}`);
      useChatStore.getState().clearUnread(convId);
    }
  }, [pathname]);

  useEffect(() => {
    if (!isStreaming) return;
    const notificationsSupported = typeof Notification !== "undefined";

    // Freeze the workspace segment at stream start: the cleanup below runs
    // arbitrarily later, and pathnameRef tracks wherever the user has since
    // navigated — possibly a different workspace. A conversation belongs to
    // the surface it was started on, and the two surfaces are separate
    // routes, so freeze that too (defaulting to research's segment if the
    // segment isn't a known surface, matching prior behavior).
    const segments = (pathnameRef.current ?? "").split("/");
    const workspace = segments[1] ?? "";
    const surface = SURFACE_SEGMENTS.includes(segments[2]) ? segments[2] : SURFACES.research.segment;

    // Rising edge: one-time permission offer if the answer is slow.
    const timer = setTimeout(() => {
      if (!notificationsSupported) return;
      const s = useChatStore.getState();
      if (!s.isStreaming) return;
      if (Notification.permission !== "default") return; // already granted/denied
      if (localStorage.getItem(DISMISS_KEY)) return;
      toast("Still working on your answer", {
        description: "Get a browser notification when it's ready?",
        duration: 10_000,
        action: {
          label: "Notify me",
          onClick: () => void Notification.requestPermission(),
        },
        onDismiss: () => localStorage.setItem(DISMISS_KEY, "1"),
      });
    }, PROMPT_AFTER_MS);

    // Falling edge (cleanup fires when isStreaming flips false): notify if
    // the user isn't looking. doneEvent==null means stop/abort/error — skip.
    return () => {
      clearTimeout(timer);
      const s = useChatStore.getState();
      if (s.isStreaming) return; // effect re-run/unmount, not completion
      if (!s.doneEvent) return;
      const convId = s.streamingConversationId;
      if (!convId) return;
      const path = pathnameRef.current ?? "";
      const onConvRoute = path.includes(`/${surface}/${convId}`);
      if (onConvRoute && !document.hidden) return; // watching — nothing to signal

      const goToConversation = () => {
        window.focus();
        router.push(`/${workspace}/${surface}/${convId}`);
      };

      // In-app channel: sticky toast + unread dot, unless the conversation
      // is already open (the answer greets them the moment they return).
      if (!onConvRoute) {
        useChatStore.getState().markUnread(convId);
        toast.success("Answer ready", {
          id: `chat-ready-${convId}`, // one per conversation — newer replaces older
          description: s.streamingContent.slice(0, 80) || undefined,
          duration: Infinity,
          action: { label: "View", onClick: goToConversation },
        });
      }

      // OS channel: only a backgrounded tab needs it.
      if (
        notificationsSupported &&
        document.hidden &&
        Notification.permission === "granted"
      ) {
        const n = new Notification("Answer ready", {
          body: s.streamingContent.slice(0, 120) || "Your chat answer is ready.",
          tag: convId, // replaces stale notifications for the same conversation
        });
        n.onclick = () => {
          goToConversation();
          n.close();
        };
      }
    };
  }, [isStreaming, router]);

  return null;
}
