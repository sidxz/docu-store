"use client";

import { use } from "react";
import { ChatLayout } from "@/components/chat/ChatLayout";

export default function ConversationPage({
  params,
}: {
  params: Promise<{ workspace: string; conversationId: string }>;
}) {
  const { workspace, conversationId } = use(params);

  return (
    <div className="-m-6 h-[calc(100%+3rem)]">
      <ChatLayout workspace={workspace} conversationId={conversationId} />
    </div>
  );
}
