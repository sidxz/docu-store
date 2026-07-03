import type { DragEvent } from "react";

/** Shared drag-and-drop protocol for moving chats into folders. */
export const CHAT_ID = "application/x-chat-id";
export const CHAT_FROM = "application/x-chat-from";

/** Stamp a drag event with the chat id + source folder ("" when unfiled). */
export function setChatDragData(
  e: DragEvent,
  chatId: string,
  fromFolderId: string | null,
) {
  e.dataTransfer.setData(CHAT_ID, chatId);
  e.dataTransfer.setData(CHAT_FROM, fromFolderId ?? "");
  e.dataTransfer.effectAllowed = "move";
}
