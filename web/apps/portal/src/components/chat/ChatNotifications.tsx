"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";
import { useChatStore } from "@/lib/stores/chat-store";

const DISMISS_KEY = "chat-notify-dismissed";
const PROMPT_AFTER_MS = 12_000;

/**
 * Null-rendering listener mounted in the workspace layout (it must outlive
 * the chat routes). Two jobs:
 * 1. When a stream drags past ~12s, offer browser notifications once.
 * 2. When an answer completes while the user is elsewhere (tab hidden or
 *    on another route), fire a native Notification that links back.
 */
export function ChatNotifications() {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const router = useRouter();
  const pathname = usePathname();
  const pathnameRef = useRef(pathname);
  pathnameRef.current = pathname;

  useEffect(() => {
    if (typeof Notification === "undefined") return; // unsupported browser
    if (!isStreaming) return;

    // Rising edge: one-time permission offer if the answer is slow.
    const timer = setTimeout(() => {
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
      if (Notification.permission !== "granted") return;
      const convId = s.streamingConversationId;
      if (!convId) return;
      const path = pathnameRef.current ?? "";
      const viewing = !document.hidden && path.includes(`/chat/${convId}`);
      if (viewing) return;
      const workspace = path.split("/")[1] ?? "";
      const n = new Notification("Answer ready", {
        body: s.streamingContent.slice(0, 120) || "Your chat answer is ready.",
        tag: convId, // replaces stale notifications for the same conversation
      });
      n.onclick = () => {
        window.focus();
        router.push(`/${workspace}/chat/${convId}`);
        n.close();
      };
    };
  }, [isStreaming, router]);

  return null;
}
